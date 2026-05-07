import uuid

from app.domain.entities.facial_expression_question_result import FacialExpressionQuestionResult
from app.domain.entities.facial_expression_session import FacialExpressionSession


def test_facial_expression_session_defaults():
    s = FacialExpressionSession(
        user_id=uuid.uuid4(),
        baseline_pucker=0.05,
        baseline_brow_down=0.08,
        baseline_lips_down=0.04,
    )
    assert s.id is not None
    assert s.overall_score is None
    assert s.created_at is not None
    assert s.baseline_pucker == 0.05
    assert s.baseline_brow_down == 0.08
    assert s.baseline_lips_down == 0.04


def test_facial_expression_question_result_defaults():
    r = FacialExpressionQuestionResult(
        session_id=uuid.uuid4(),
        question_id="q1",
        question_text="¿Cuéntanos sobre tu experiencia?",
        duration_ms=28000,
        frames=[],
    )
    assert r.id is not None
    assert r.pucker_score is None
    assert r.brow_down_score is None
    assert r.lips_down_score is None
    assert r.question_score is None
    assert r.question_id == "q1"
    assert r.duration_ms == 28000
    assert r.created_at is not None
    assert r.frames == []
