# Both get_session and get_current_user are overridden via app.dependency_overrides.
# FastAPI resolves dependencies through its DI container by function identity, so
# patching the module path does not intercept them — dependency_overrides does.
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from main import app


def _make_user():
    u = MagicMock()
    u.id = "00000000-0000-0000-0000-000000000001"
    u.is_active = True
    return u


VALID_PAYLOAD = {
    "duration_ms": 10000,
    "events": [
        {"t_ms": 0, "emotion": "happy", "gestures": {"mouthSmile": 0.7}},
        {"t_ms": 5000, "emotion": "neutral", "gestures": {}},
    ],
}


@pytest.mark.asyncio
async def test_create_session_returns_201():
    mock_session_obj = MagicMock()
    mock_session_obj.id = "00000000-0000-0000-0000-000000000002"
    mock_session_obj.duration_ms = 10000
    mock_session_obj.dominant_emotion = "happy"
    mock_session_obj.dominant_percentage = 50
    mock_session_obj.emotion_distribution = {"happy": 50, "neutral": 50}
    mock_session_obj.created_at.isoformat.return_value = "2026-05-07T00:00:00+00:00"
    mock_session_obj.events = []

    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with (
            patch(
                "app.presentation.routers.facial_expression.save_facial_expression_session",
                new_callable=AsyncMock,
                return_value=mock_session_obj,
            ),
            patch(
                "app.presentation.routers.facial_expression.get_facial_expression_session",
                new_callable=AsyncMock,
                return_value=mock_session_obj,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/facial-expression/sessions",
                    json=VALID_PAYLOAD,
                    headers={"Authorization": "Bearer faketoken"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["id"]
    assert data["dominant_emotion"] == "happy"
    assert data["emotion_distribution"] == {"happy": 50, "neutral": 50}


@pytest.mark.asyncio
async def test_get_session_not_found():
    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with patch(
            "app.presentation.routers.facial_expression.get_facial_expression_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/facial-expression/sessions/00000000-0000-0000-0000-000000000099",
                    headers={"Authorization": "Bearer faketoken"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_session_invalid_uuid_returns_404():
    """A malformed session_id must produce 404, not crash the database driver."""
    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/facial-expression/sessions/not-a-uuid",
                headers={"Authorization": "Bearer faketoken"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_session_rejects_unknown_emotion():
    """Emotions outside the allow-list must return 422."""
    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    bad_payload = {
        "duration_ms": 5000,
        "events": [
            {"t_ms": 0, "emotion": "bored", "gestures": {}},
        ],
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/facial-expression/sessions",
                json=bad_payload,
                headers={"Authorization": "Bearer faketoken"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_session_rejects_negative_t_ms():
    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    bad_payload = {
        "duration_ms": 5000,
        "events": [{"t_ms": -1, "emotion": "happy", "gestures": {}}],
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/facial-expression/sessions",
                json=bad_payload,
                headers={"Authorization": "Bearer faketoken"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_session_rolls_back_on_use_case_error():
    """If the use case raises, the router must call session.rollback before re-raising."""
    mock_session = AsyncMock()

    async def override_get_session():
        yield mock_session

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with patch(
            "app.presentation.routers.facial_expression.save_facial_expression_session",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/facial-expression/sessions",
                    json=VALID_PAYLOAD,
                    headers={"Authorization": "Bearer faketoken"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    mock_session.rollback.assert_awaited_once()
