from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


def _make_fake_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@okaction.local"
    user.is_active = True
    return user


def _make_fake_session_record(user_id):
    from datetime import datetime, timezone
    record = MagicMock()
    record.id = uuid.uuid4()
    record.user_id = user_id
    record.level = "basico"
    record.overall_score = 80.0
    record.vowel_score = 82.0
    record.consonant_score = 78.0
    record.fluency_score = 81.0
    record.intelligibility_score = 79.0
    record.summary_feedback = "Buena pronunciacion general."
    record.created_at = datetime.now(timezone.utc)
    record.phrase_pronunciations = []
    return record


@pytest.mark.asyncio
async def test_save_pronunciation_session():
    from app.use_cases.pronunciation.sessions import save_pronunciation_session
    from app.domain.entities.pronunciation_session import PronunciationSession

    fake_user = _make_fake_user()

    saved_record = MagicMock(spec=PronunciationSession)
    saved_record.id = uuid.uuid4()
    saved_record.phrase_pronunciations = []

    fake_db = AsyncMock()
    fake_db.flush = AsyncMock()
    fake_db.refresh = AsyncMock()
    fake_db.commit = AsyncMock()
    fake_db.add = MagicMock()

    async def fake_refresh(obj):
        if isinstance(obj, PronunciationSession):
            obj.id = saved_record.id
            obj.phrase_pronunciations = []

    fake_db.refresh.side_effect = fake_refresh

    data = {
        "level": "basico",
        "overall_score": 80.0,
        "vowel_score": 82.0,
        "consonant_score": 78.0,
        "fluency_score": 81.0,
        "intelligibility_score": 79.0,
        "summary_feedback": "Buena pronunciacion.",
        "evaluations": [],
    }

    result = await save_pronunciation_session(data, fake_user, fake_db)
    fake_db.commit.assert_called_once()
