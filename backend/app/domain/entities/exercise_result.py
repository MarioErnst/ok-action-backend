import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class ExerciseResult(Base):
    __tablename__ = "exercise_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("phonation_sessions.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[str] = mapped_column(String(50), nullable=False)
    exercise_type: Mapped[str] = mapped_column(String(20), nullable=False)
    avg_hz: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    stability: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    breaks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_range: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["PhonationSession"] = relationship(back_populates="exercise_results")
