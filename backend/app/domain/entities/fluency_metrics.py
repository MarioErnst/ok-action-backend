from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class FluencyMetrics(Base):
    __tablename__ = "fluency_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    fluency_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    stuck_events_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    words_per_minute: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("fluency_score BETWEEN 0 AND 100", name="ck_fluency_score"),
    )
