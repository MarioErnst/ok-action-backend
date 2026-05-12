from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base
from app.domain.entities.enums import ModuleEnum, SessionStatusEnum


class Session(Base):
    """Root table for every session of every module.

    A live session is just a row with module='live'; its component module
    sessions are children pointing back through parent_id.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    module: Mapped[ModuleEnum] = mapped_column(
        SQLEnum(ModuleEnum, name="module_enum", create_type=False), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    status: Mapped[SessionStatusEnum] = mapped_column(
        SQLEnum(SessionStatusEnum, name="session_status_enum", create_type=False),
        nullable=False,
        default=SessionStatusEnum.active,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    parent: Mapped["Session | None"] = relationship(
        "Session", remote_side="Session.id", back_populates="children"
    )
    children: Mapped[list["Session"]] = relationship(back_populates="parent")

    __table_args__ = (
        CheckConstraint(
            "score IS NULL OR (score BETWEEN 0 AND 100)",
            name="ck_sessions_score_range",
        ),
        CheckConstraint(
            "(status = 'active') = (ended_at IS NULL)",
            name="ck_sessions_active_ended",
        ),
        Index("ix_sessions_user_started", "user_id", "started_at"),
        Index("ix_sessions_user_module_started", "user_id", "module", "started_at"),
        Index("ix_sessions_parent", "parent_id"),
        Index("ix_sessions_module_status", "module", "status"),
    )
