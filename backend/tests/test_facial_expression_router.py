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
    "baseline": {"pucker": 0.05, "brow_down": 0.08, "lips_down": 0.04},
    "questions": [
        {
            "question_id": "q1",
            "question_text": "¿Cuéntanos sobre tu experiencia?",
            "duration_ms": 20000,
            "frames": [
                {"t": 0, "pk": 0.06, "bd": 0.09, "ld": 0.05},
                {"t": 66, "pk": 0.07, "bd": 0.08, "ld": 0.04},
            ],
        }
    ],
}


@pytest.mark.asyncio
async def test_create_session_returns_201():
    mock_session_obj = MagicMock()
    mock_session_obj.id = "00000000-0000-0000-0000-000000000002"
    mock_session_obj.overall_score = 95
    mock_session_obj.created_at.isoformat.return_value = "2026-05-07T00:00:00+00:00"
    mock_session_obj.question_results = []

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
    assert "id" in data
    assert "overall_score" in data


@pytest.mark.asyncio
async def test_get_session_not_found():
    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with (
            patch(
                "app.presentation.routers.facial_expression.get_facial_expression_session",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/facial-expression/sessions/nonexistent",
                    headers={"Authorization": "Bearer faketoken"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
