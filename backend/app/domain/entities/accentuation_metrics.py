from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class AccentuationMetrics(Base):
    __tablename__ = "accentuation_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    pronunciation_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rhythm_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    intonation_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    stress_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    phrases_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(
            "pronunciation_score BETWEEN 0 AND 100",
            name="ck_accentuation_pronunciation_score",
        ),
        CheckConstraint("rhythm_score BETWEEN 0 AND 100", name="ck_accentuation_rhythm_score"),
        CheckConstraint("intonation_score BETWEEN 0 AND 100", name="ck_accentuation_intonation_score"),
        CheckConstraint("stress_score BETWEEN 0 AND 100", name="ck_accentuation_stress_score"),
    )
