from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class PhonationMetrics(Base):
    """Aggregated phonation metrics for a session (1:1 with sessions)."""

    __tablename__ = "phonation_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    avg_hz: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    stability_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    breaks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exercises_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(
            "stability_score BETWEEN 0 AND 100",
            name="ck_phonation_metrics_stability_range",
        ),
    )
