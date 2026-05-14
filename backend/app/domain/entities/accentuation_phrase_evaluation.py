from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class AccentuationPhraseEvaluation(Base):
    """One persisted phrase evaluation inside an accentuation session.

    Composite PK (session_id, phrase_index) matches the schema convention
    used by precision_rounds and linguistic_versatility_rounds. prompt_id
    is a hard FK with ON DELETE RESTRICT: removing a phrase from the catalog
    is blocked while any session still references it. The four sub-scores
    are the same dimensions the session-level metrics row aggregates;
    persisting them per-phrase enables the insights/weakest-prompts query
    without storing any LLM-generated text.
    """

    __tablename__ = "accentuation_phrase_evaluations"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    phrase_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompts.id", ondelete="RESTRICT"), nullable=False
    )
    pronunciation_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rhythm_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    intonation_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    stress_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "pronunciation_score BETWEEN 0 AND 100",
            name="ck_acc_phrase_pronunciation_score",
        ),
        CheckConstraint(
            "rhythm_score BETWEEN 0 AND 100",
            name="ck_acc_phrase_rhythm_score",
        ),
        CheckConstraint(
            "intonation_score BETWEEN 0 AND 100",
            name="ck_acc_phrase_intonation_score",
        ),
        CheckConstraint(
            "stress_score BETWEEN 0 AND 100",
            name="ck_acc_phrase_stress_score",
        ),
        CheckConstraint(
            "phrase_index >= 0",
            name="ck_acc_phrase_index_non_negative",
        ),
    )
