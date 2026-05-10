from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class MuletillasMetrics(Base):
    __tablename__ = "muletillas_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    fluency_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    muletillas_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("fluency_score BETWEEN 0 AND 100", name="ck_muletillas_fluency_score"),
    )
