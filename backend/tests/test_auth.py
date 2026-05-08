from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


def _make_fake_user():
    from app.infrastructure.security.hashing import hash_password

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@okaction.local"
    user.password_hash = hash_password("password123")
    user.full_name = "Usuario Demo"
    user.is_active = True
    return user


@pytest.mark.asyncio
async def test_login_success():
    fake_user = _make_fake_user()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_user

    fake_session = AsyncMock()
    fake_session.execute.return_value = fake_result

    async def override_get_session():
        yield fake_session

    app.dependency_overrides.clear()
    from app.infrastructure.db.session import get_session
    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "email": "test@okaction.local",
            "password": "password123",
        })

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "test@okaction.local"
    assert data["user"]["full_name"] == "Usuario Demo"
    assert data["user"]["is_active"] is True
    assert "id" in data["user"]


@pytest.mark.asyncio
async def test_login_wrong_password():
    fake_user = _make_fake_user()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_user

    fake_session = AsyncMock()
    fake_session.execute.return_value = fake_result

    async def override_get_session():
        yield fake_session

    app.dependency_overrides.clear()
    from app.infrastructure.db.session import get_session
    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "email": "test@okaction.local",
            "password": "wrongpassword",
        })

    app.dependency_overrides.clear()

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_user_not_found():
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = None

    fake_session = AsyncMock()
    fake_session.execute.return_value = fake_result

    async def override_get_session():
        yield fake_session

    app.dependency_overrides.clear()
    from app.infrastructure.db.session import get_session
    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "email": "nobody@example.com",
            "password": "password123",
        })

    app.dependency_overrides.clear()

    assert response.status_code == 401
