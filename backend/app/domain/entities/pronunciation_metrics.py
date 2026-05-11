from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class PronunciationMetrics(Base):
    __tablename__ = "pronunciation_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    vowel_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    consonant_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fluency_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    intelligibility_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    phrases_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("vowel_score BETWEEN 0 AND 100", name="ck_pronunciation_vowel_score"),
        CheckConstraint(
            "consonant_score BETWEEN 0 AND 100", name="ck_pronunciation_consonant_score"
        ),
        CheckConstraint("fluency_score BETWEEN 0 AND 100", name="ck_pronunciation_fluency_score"),
        CheckConstraint(
            "intelligibility_score BETWEEN 0 AND 100",
            name="ck_pronunciation_intelligibility_score",
        ),
    )
