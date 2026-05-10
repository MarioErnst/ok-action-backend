from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class ConsistencyMetrics(Base):
    __tablename__ = "consistency_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    consistency_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    volatility_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    active_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "consistency_score BETWEEN 0 AND 100",
            name="ck_consistency_score",
        ),
        CheckConstraint(
            "volatility_score BETWEEN 0 AND 100",
            name="ck_consistency_volatility_score",
        ),
        CheckConstraint("active_pct BETWEEN 0 AND 100", name="ck_consistency_active_pct"),
    )
