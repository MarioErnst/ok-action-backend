from app.domain.entities.facial_expression_session import FacialExpressionSession
from app.domain.entities.facial_expression_emotion_event import (
    FacialExpressionEmotionEvent,
)


def test_session_defaults():
    s = FacialExpressionSession(
        user_id="00000000-0000-0000-0000-000000000001",
        duration_ms=10000,
    )
    assert s.id is not None
    assert s.created_at is not None
    assert s.emotion_distribution == {}
    assert s.dominant_emotion is None
    assert s.dominant_percentage is None


def test_event_defaults():
    e = FacialExpressionEmotionEvent(
        session_id="00000000-0000-0000-0000-000000000001",
        t_ms=1234,
        emotion="happy",
    )
    assert e.id is not None
    assert e.gestures == {}
