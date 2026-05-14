from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class PauseMetrics(Base):
    __tablename__ = "pause_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    pauses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pause_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    longest_pause_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    silence_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Optional FK to the prompts catalog: identifies what the user practiced.
    # RESTRICT prevents deleting a prompt that still has sessions linked to it.
    # NULL is allowed for legacy rows captured before the catalog migration.
    prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompts.id", ondelete="RESTRICT"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("silence_pct BETWEEN 0 AND 100", name="ck_pause_silence_pct"),
    )
