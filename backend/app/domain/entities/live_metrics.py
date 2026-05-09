from __future__ import annotations

import uuid

from sqlalchemy import Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.domain.entities.enums import StopReasonEnum


class LiveMetrics(Base):
    """Per-live-session data. The live session's children (component module sessions)
    are obtained via SELECT * FROM sessions WHERE parent_id = <live_id>.
    """

    __tablename__ = "live_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    stop_reason: Mapped[StopReasonEnum] = mapped_column(
        SQLEnum(StopReasonEnum, name="stop_reason_enum", create_type=False), nullable=False
    )
