from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class LoudnessMetrics(Base):
    """Aggregated loudness metrics for a session (1:1 with sessions)."""

    __tablename__ = "loudness_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    preset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loudness_presets.id", ondelete="RESTRICT"), nullable=False
    )
    optimal_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    low_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    high_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    clipping_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    peak_db: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    # Ambient noise floor measured by a short pre-session calibration window
    # on the client. Used by the frontend to render an absolute reference for
    # the bands and by analytics to compare sessions across mics/environments.
    # NULL on rows persisted before the calibration UX rolled out.
    noise_floor_db: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )

    __table_args__ = (
        CheckConstraint("optimal_pct BETWEEN 0 AND 100", name="ck_loudness_optimal_pct"),
        CheckConstraint("low_pct BETWEEN 0 AND 100", name="ck_loudness_low_pct"),
        CheckConstraint("high_pct BETWEEN 0 AND 100", name="ck_loudness_high_pct"),
        CheckConstraint("clipping_pct BETWEEN 0 AND 100", name="ck_loudness_clipping_pct"),
        CheckConstraint(
            "optimal_pct + low_pct + high_pct + clipping_pct = 100",
            name="ck_loudness_pct_total",
        ),
    )
