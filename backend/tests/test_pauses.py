import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


def _fake_user():
    return SimpleNamespace(id=uuid.uuid4(), email="test@okaction.local", is_active=True)


def _fake_pause_session(session_id: uuid.UUID | None = None):
    return SimpleNamespace(
        id=session_id or uuid.uuid4(),
        prompt_text="Describe una experiencia presentando en publico.",
        duration_ms=18000,
        total_pauses=2,
        total_pause_duration_ms=1600,
        average_pause_ms=800,
        longest_pause_ms=1000,
        silence_ratio=0.18,
        classification="pausas adecuadas",
        pauses=[
            {"start_ms": 2400, "end_ms": 3300, "duration_ms": 900},
            {"start_ms": 7200, "end_ms": 7900, "duration_ms": 700},
        ],
        created_at=datetime.now(timezone.utc),
    )


def _pause_payload():
    return {
        "prompt_text": "Describe una experiencia presentando en publico.",
        "duration_ms": 18000,
        "pause_metrics": {
            "total_pauses": 2,
            "total_pause_duration_ms": 1600,
            "average_pause_ms": 800,
            "longest_pause_ms": 1000,
            "silence_ratio": 0.18,
            "classification": "pausas adecuadas",
            "pauses": [
                {"start_ms": 2400, "end_ms": 3300, "duration_ms": 900},
                {"start_ms": 7200, "end_ms": 7900, "duration_ms": 700},
            ],
        },
    }


def _install_dependency_overrides(user):
    from app.infrastructure.db.session import get_session
    from app.infrastructure.security.dependencies import get_current_user

    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return user

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user


@pytest.mark.asyncio
async def test_create_pause_session(monkeypatch):
    import app.presentation.routers.pauses as pauses_router

    user = _fake_user()
    fake_session = _fake_pause_session()
    _install_dependency_overrides(user)

    async def fake_save_pause_session(data, user, session):
        return fake_session

    monkeypatch.setattr(pauses_router, "save_pause_session", fake_save_pause_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/pauses/sessions", json=_pause_payload())

    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["prompt_text"] == fake_session.prompt_text
    assert data["pause_metrics"]["total_pauses"] == 2
    assert data["pause_metrics"]["pauses"][0]["duration_ms"] == 900


@pytest.mark.asyncio
async def test_list_pause_sessions(monkeypatch):
    import app.presentation.routers.pauses as pauses_router

    user = _fake_user()
    fake_session = _fake_pause_session()
    _install_dependency_overrides(user)

    async def fake_list_pause_sessions(user, session):
        return [fake_session]

    monkeypatch.setattr(pauses_router, "list_pause_sessions", fake_list_pause_sessions)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/pauses/sessions")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["total_pauses"] == 2
    assert data[0]["classification"] == "pausas adecuadas"


@pytest.mark.asyncio
async def test_get_pause_session_not_found(monkeypatch):
    import app.presentation.routers.pauses as pauses_router

    user = _fake_user()
    _install_dependency_overrides(user)

    async def fake_get_pause_session(session_id, user, session):
        return None

    monkeypatch.setattr(pauses_router, "get_pause_session", fake_get_pause_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/pauses/sessions/{uuid.uuid4()}")

    app.dependency_overrides.clear()

    assert response.status_code == 404
