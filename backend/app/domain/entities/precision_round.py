from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class PrecisionRound(Base):
    __tablename__ = "precision_rounds"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    round_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompts.id", ondelete="RESTRICT"), nullable=False
    )
    score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    relevance_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    directness_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    conciseness_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_audio_intelligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "score IS NULL OR (score BETWEEN 0 AND 100)",
            name="ck_precision_round_score",
        ),
        CheckConstraint(
            "relevance_score IS NULL OR (relevance_score BETWEEN 0 AND 100)",
            name="ck_precision_round_relevance",
        ),
        CheckConstraint(
            "directness_score IS NULL OR (directness_score BETWEEN 0 AND 100)",
            name="ck_precision_round_directness",
        ),
        CheckConstraint(
            "conciseness_score IS NULL OR (conciseness_score BETWEEN 0 AND 100)",
            name="ck_precision_round_conciseness",
        ),
        Index("ix_precision_rounds_prompt", "prompt_id"),
    )
