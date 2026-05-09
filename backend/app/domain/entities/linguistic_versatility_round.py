from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class LinguisticVersatilityRound(Base):
    __tablename__ = "linguistic_versatility_rounds"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    round_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompts.id", ondelete="RESTRICT"), nullable=True
    )
    score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    vocabulary_richness: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_audio_intelligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "score IS NULL OR (score BETWEEN 0 AND 100)",
            name="ck_lex_round_score",
        ),
        CheckConstraint(
            "vocabulary_richness IS NULL OR (vocabulary_richness BETWEEN 0 AND 100)",
            name="ck_lex_round_richness",
        ),
        Index("ix_lex_rounds_prompt", "prompt_id"),
    )
