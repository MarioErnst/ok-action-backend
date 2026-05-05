import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class LoudnessPreset(Base):
    __tablename__ = "loudness_presets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, default=None
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    silence_offset_db: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    too_low_offset_db: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    optimal_offset_db: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    clip_threshold_dbfs: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User | None"] = relationship(back_populates="loudness_presets")
    loudness_sessions: Mapped[list["LoudnessSession"]] = relationship(back_populates="preset")
