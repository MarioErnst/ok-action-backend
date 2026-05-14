from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class PronunciationPhraseEvaluation(Base):
    """One persisted phrase evaluation inside a pronunciation session.

    Same shape as accentuation_phrase_evaluations but with the four
    pronunciation sub-scores (vowel, consonant, fluency, intelligibility).
    Composite PK (session_id, phrase_index) keeps row uniqueness without an
    artificial UUID column; prompt_id is RESTRICT-protected so the catalog
    can't lose a phrase that has historical evaluations linked to it.
    """

    __tablename__ = "pronunciation_phrase_evaluations"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    phrase_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompts.id", ondelete="RESTRICT"), nullable=False
    )
    vowel_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    consonant_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fluency_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    intelligibility_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "vowel_score BETWEEN 0 AND 100",
            name="ck_pron_phrase_vowel_score",
        ),
        CheckConstraint(
            "consonant_score BETWEEN 0 AND 100",
            name="ck_pron_phrase_consonant_score",
        ),
        CheckConstraint(
            "fluency_score BETWEEN 0 AND 100",
            name="ck_pron_phrase_fluency_score",
        ),
        CheckConstraint(
            "intelligibility_score BETWEEN 0 AND 100",
            name="ck_pron_phrase_intelligibility_score",
        ),
        CheckConstraint(
            "phrase_index >= 0",
            name="ck_pron_phrase_index_non_negative",
        ),
    )
