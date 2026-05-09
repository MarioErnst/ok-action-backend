from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Enum as SQLEnum, ForeignKey, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.domain.entities.enums import LinguisticVersatilityModeEnum


class LinguisticVersatilityMetrics(Base):
    __tablename__ = "linguistic_versatility_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[LinguisticVersatilityModeEnum] = mapped_column(
        SQLEnum(
            LinguisticVersatilityModeEnum,
            name="linguistic_versatility_mode_enum",
            create_type=False,
        ),
        nullable=False,
        default=LinguisticVersatilityModeEnum.guided,
    )
    rounds_total: Mapped[int] = mapped_column(Integer, nullable=False)
    rounds_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vocabulary_richness_avg: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "vocabulary_richness_avg IS NULL OR (vocabulary_richness_avg BETWEEN 0 AND 100)",
            name="ck_lex_richness_avg",
        ),
    )
