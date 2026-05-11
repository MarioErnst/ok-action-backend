from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.domain.entities.enums import ExerciseTypeEnum


class PhonationSessionExercise(Base):
    """One row per exercise type within a phonation session.

    Allows longitudinal aggregates per exercise_type (e.g. user's gliding stability
    over time).
    """

    __tablename__ = "phonation_session_exercises"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    exercise_type: Mapped[ExerciseTypeEnum] = mapped_column(
        SQLEnum(ExerciseTypeEnum, name="exercise_type_enum", create_type=False),
        primary_key=True,
    )
    avg_hz: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    stability_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    breaks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_range_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "stability_score BETWEEN 0 AND 100",
            name="ck_phonation_exercise_stability_range",
        ),
        CheckConstraint(
            "in_range_pct BETWEEN 0 AND 100",
            name="ck_phonation_exercise_in_range_pct",
        ),
        Index("ix_phonation_exercises_type", "exercise_type"),
    )
