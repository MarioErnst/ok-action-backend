"""Shared fixtures for the test suite.

Tests run against the real Cloud SQL database used in development. Each
test that mutates state inserts and cleans up its own session rows; the
session_cleanup fixture wipes any sessions the dev user owns when the
test exits, so a failing test cannot leave the DB dirty for the next.

We do not spin up a separate test database because:
- the dev DB is already isolated from prod and rebuilt by alembic migrations,
- spinning up a fresh PG instance per run would burn the cache window we
  rely on for fast iteration, and
- the schema invariants we want to verify (CHECK constraints, FK CASCADEs)
  only exist in PG, not in a stub.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.session import Session as SessionEntity
from app.domain.entities.user import User
from app.infrastructure.db.session import async_session_factory, dispose_connector
from main import app


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """One event loop per test session. Required because dispose_connector
    closes the singleton Cloud SQL connector and we cannot recreate it
    cleanly across loops.
    """

    loop = asyncio.new_event_loop()
    yield loop
    loop.run_until_complete(dispose_connector())
    loop.close()


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def dev_user(db: AsyncSession) -> User:
    """The seeded dev user. Tests use it as the authenticated identity."""

    user = (
        await db.execute(select(User).where(User.email == "test@okaction.local"))
    ).scalar_one()
    return user


@pytest_asyncio.fixture
async def session_cleanup(dev_user: User) -> AsyncIterator[None]:
    """Wipe every session owned by the dev user when the test ends.

    Runs as a best-effort sweep so a failing test cannot poison subsequent
    runs. CASCADE on session children + their metrics rows handles the
    transitive deletes.
    """

    yield
    async with async_session_factory() as cleanup_db:
        await cleanup_db.execute(
            delete(SessionEntity).where(SessionEntity.user_id == dev_user.id)
        )
        await cleanup_db.commit()


@pytest_asyncio.fixture
async def auth_token(dev_user: User) -> str:
    """JWT for the dev user. Build it via the auth use_case so the token
    matches whatever encoding the live app uses."""

    from app.infrastructure.security.jwt import create_access_token

    return create_access_token(str(dev_user.id))


@pytest_asyncio.fixture
async def client(auth_token: str) -> AsyncIterator[AsyncClient]:
    """An httpx AsyncClient pre-configured with the Bearer token so tests
    do not have to repeat the header on every call."""

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {auth_token}"},
    ) as c:
        yield c


@pytest_asyncio.fixture
async def anon_client() -> AsyncIterator[AsyncClient]:
    """Same client without the auth header, for testing 401 paths."""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
