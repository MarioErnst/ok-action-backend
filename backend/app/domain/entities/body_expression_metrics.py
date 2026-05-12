from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Enum as SQLEnum, ForeignKey, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.enums import BodyFramingModeEnum
from app.infrastructure.db.base import Base


class BodyExpressionMetrics(Base):
    __tablename__ = "body_expression_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    posture_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    openness_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    gesture_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    stability_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    energy_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    framing_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tracked_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hands_visible_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    excessive_movement_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    calibration_quality_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    framing_mode: Mapped[BodyFramingModeEnum] = mapped_column(
        SQLEnum(BodyFramingModeEnum, name="body_framing_mode_enum", create_type=False),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("posture_score BETWEEN 0 AND 100", name="ck_body_posture_score"),
        CheckConstraint("openness_score BETWEEN 0 AND 100", name="ck_body_openness_score"),
        CheckConstraint("gesture_score BETWEEN 0 AND 100", name="ck_body_gesture_score"),
        CheckConstraint("stability_score BETWEEN 0 AND 100", name="ck_body_stability_score"),
        CheckConstraint("energy_score BETWEEN 0 AND 100", name="ck_body_energy_score"),
        CheckConstraint("framing_score BETWEEN 0 AND 100", name="ck_body_framing_score"),
        CheckConstraint("tracked_pct BETWEEN 0 AND 100", name="ck_body_tracked_pct"),
        CheckConstraint("hands_visible_pct BETWEEN 0 AND 100", name="ck_body_hands_visible_pct"),
        CheckConstraint(
            "excessive_movement_pct BETWEEN 0 AND 100",
            name="ck_body_excessive_movement_pct",
        ),
        CheckConstraint(
            "calibration_quality_pct BETWEEN 0 AND 100",
            name="ck_body_calibration_quality_pct",
        ),
    )
