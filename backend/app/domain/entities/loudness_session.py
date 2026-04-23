import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class LoudnessSession(Base):
    __tablename__ = "loudness_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    preset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loudness_presets.id", ondelete="SET NULL"), nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    optimal_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    peak_db: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    band_time_ms: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="loudness_sessions")
    preset: Mapped["LoudnessPreset"] = relationship(back_populates="loudness_sessions")
