"""Router tests with Gemini mocked.

The Gemini service is patched at the module path used by each use case so the
real network call never happens. get_session and get_current_user are
overridden via FastAPI's dependency_overrides because patch() does not
intercept dependencies resolved through the DI container.
"""
import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from main import app


def _make_user():
    u = MagicMock()
    u.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    u.is_active = True
    return u


def _audio_field() -> tuple[str, io.BytesIO, str]:
    """Return a multipart-friendly tuple for a fake audio file."""
    return ("answer.webm", io.BytesIO(b"\x00\x01\x02\x03"), "audio/webm")


@pytest.mark.asyncio
async def test_start_session_returns_questions():
    mock_session_obj = MagicMock()
    mock_session_obj.id = uuid.UUID("00000000-0000-0000-0000-000000000010")
    mock_session_obj.total_rounds = 3
    mock_q1 = MagicMock(
        id=uuid.UUID("00000000-0000-0000-0000-000000000020"),
        text="Q1?",
        category="personal_experience",
        difficulty_level="basic",
    )

    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with patch(
            "app.presentation.routers.linguistic_versatility.start_versatility_session",
            new_callable=AsyncMock,
            return_value=(mock_session_obj, [mock_q1]),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/linguistic-versatility/sessions",
                    headers={"Authorization": "Bearer faketoken"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["session_id"]
    assert data["total_rounds"] == 3
    assert len(data["questions"]) == 1


@pytest.mark.asyncio
async def test_evaluate_round_returns_score():
    mock_round = MagicMock(
        id=uuid.UUID("00000000-0000-0000-0000-000000000030"),
        audio_intelligible=True,
        versatility_score=72,
        vocabulary_richness=2,
        feedback="Buena variedad de verbos.",
    )
    mock_session = MagicMock(completed_rounds=1, total_rounds=3)
    mock_question = MagicMock(text="¿Cómo te fue hoy?")

    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    sid = uuid.UUID("00000000-0000-0000-0000-000000000010")
    qid = uuid.UUID("00000000-0000-0000-0000-000000000020")

    try:
        # The router fetches the question first (db.get) and then calls the
        # use case. Mock both so the flow runs without a real DB or Gemini.
        with patch(
            "app.presentation.routers.linguistic_versatility.evaluate_versatility_response",
            new_callable=AsyncMock,
            return_value=mock_round,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # db.get is on the session yielded above; patch its return.
                async def fake_get(model, key):
                    return mock_question if "Question" in model.__name__ else mock_session

                client_session = await override_get_session().__anext__()
                client_session.get = AsyncMock(side_effect=fake_get)
                # Re-register override so the patched session is used.
                async def override_with_patched():
                    yield client_session

                app.dependency_overrides[get_session] = override_with_patched

                name, content, mime = _audio_field()
                response = await client.post(
                    f"/linguistic-versatility/sessions/{sid}/rounds",
                    files={"audio": (name, content, mime)},
                    data={"question_id": str(qid)},
                    headers={"Authorization": "Bearer faketoken"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["versatility_score"] == 72
    assert data["vocabulary_richness"] == 2
    assert data["completed_rounds"] == 1


@pytest.mark.asyncio
async def test_evaluate_round_rejects_invalid_question_uuid():
    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    sid = uuid.UUID("00000000-0000-0000-0000-000000000010")

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            name, content, mime = _audio_field()
            response = await client.post(
                f"/linguistic-versatility/sessions/{sid}/rounds",
                files={"audio": (name, content, mime)},
                data={"question_id": "not-a-uuid"},
                headers={"Authorization": "Bearer faketoken"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_session_not_found():
    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    sid = uuid.UUID("00000000-0000-0000-0000-000000000099")

    try:
        with patch(
            "app.presentation.routers.linguistic_versatility.get_versatility_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    f"/linguistic-versatility/sessions/{sid}",
                    headers={"Authorization": "Bearer faketoken"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_free_session_returns_score():
    mock_session = MagicMock(id=uuid.UUID("00000000-0000-0000-0000-000000000050"))
    mock_round = MagicMock(
        versatility_score=84,
        vocabulary_richness=3,
        feedback="Vocabulario rico y variado.",
        audio_intelligible=True,
    )

    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with patch(
            "app.presentation.routers.linguistic_versatility.evaluate_free_versatility_session",
            new_callable=AsyncMock,
            return_value=(mock_session, mock_round),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                name, content, mime = _audio_field()
                response = await client.post(
                    "/linguistic-versatility/free",
                    files={"audio": (name, content, mime)},
                    headers={"Authorization": "Bearer faketoken"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["versatility_score"] == 84
    assert data["vocabulary_richness"] == 3
    assert data["audio_intelligible"] is True


@pytest.mark.asyncio
async def test_free_session_rejects_oversized_audio():
    async def override_get_session():
        yield AsyncMock()

    async def override_get_current_user():
        return _make_user()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    # 6 MB exceeds the 5 MB MAX_AUDIO_BYTES cap.
    big_audio = io.BytesIO(b"\x00" * (6 * 1024 * 1024))

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/linguistic-versatility/free",
                files={"audio": ("big.webm", big_audio, "audio/webm")},
                headers={"Authorization": "Bearer faketoken"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 413
