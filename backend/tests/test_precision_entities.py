import uuid
from datetime import datetime, timezone

from app.domain.entities.precision_question import PrecisionQuestion
from app.domain.entities.precision_session import PrecisionSession
from app.domain.entities.precision_round import PrecisionRound


def test_precision_question_defaults():
    q = PrecisionQuestion()
    assert q.is_active is True
    assert q.id is not None


def test_precision_session_defaults():
    s = PrecisionSession(total_rounds=5)
    assert s.status == "active"
    assert s.completed_rounds == 0
    assert s.overall_score is None


def test_precision_round_nullable_scores():
    r = PrecisionRound(
        session_id=uuid.uuid4(),
        question_id=uuid.uuid4(),
        question_text="test",
    )
    assert r.overall_score is None
    assert r.audio_intelligible is False
