from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Enum as SQLEnum, ForeignKey, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.domain.entities.enums import PrecisionModeEnum


class PrecisionMetrics(Base):
    __tablename__ = "precision_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[PrecisionModeEnum] = mapped_column(
        SQLEnum(PrecisionModeEnum, name="precision_mode_enum", create_type=False),
        nullable=False,
        default=PrecisionModeEnum.standalone,
    )
    rounds_total: Mapped[int] = mapped_column(Integer, nullable=False)
    rounds_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relevance_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    directness_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    conciseness_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "relevance_score IS NULL OR (relevance_score BETWEEN 0 AND 100)",
            name="ck_precision_relevance_score",
        ),
        CheckConstraint(
            "directness_score IS NULL OR (directness_score BETWEEN 0 AND 100)",
            name="ck_precision_directness_score",
        ),
        CheckConstraint(
            "conciseness_score IS NULL OR (conciseness_score BETWEEN 0 AND 100)",
            name="ck_precision_conciseness_score",
        ),
    )
