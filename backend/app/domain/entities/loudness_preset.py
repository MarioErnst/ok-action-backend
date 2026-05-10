from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class LoudnessPreset(Base):
    """Microphone calibration profile. user_id NULL means a system-wide preset."""

    __tablename__ = "loudness_presets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    silence_offset_db: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    low_offset_db: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    optimal_offset_db: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    clip_threshold_db: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User | None"] = relationship(back_populates="loudness_presets")

    __table_args__ = (
        Index("ix_loudness_presets_user", "user_id"),
        Index("ix_loudness_presets_default", "is_default"),
    )
