from app.domain.entities.linguistic_versatility_question import (
    LinguisticVersatilityQuestion,
)
from app.domain.entities.linguistic_versatility_round import (
    LinguisticVersatilityRound,
)
from app.domain.entities.linguistic_versatility_session import (
    LinguisticVersatilitySession,
)


def test_question_defaults():
    q = LinguisticVersatilityQuestion(text="¿Qué hiciste hoy?", category="personal")
    assert q.id is not None
    assert q.is_active is True
    assert q.difficulty_level == "basic"
    assert q.created_at is not None


def test_session_defaults():
    s = LinguisticVersatilitySession(
        user_id="00000000-0000-0000-0000-000000000001",
        total_rounds=3,
    )
    assert s.id is not None
    assert s.mode == "guided"
    assert s.status == "active"
    assert s.completed_rounds == 0
    assert s.overall_score is None
    assert s.completed_at is None


def test_round_defaults():
    r = LinguisticVersatilityRound(
        session_id="00000000-0000-0000-0000-000000000001",
    )
    assert r.id is not None
    assert r.audio_intelligible is False
    assert r.versatility_score is None
    assert r.vocabulary_richness is None
    assert r.question_id is None
    assert r.created_at is not None
