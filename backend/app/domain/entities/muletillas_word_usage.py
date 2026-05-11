from __future__ import annotations

import uuid

from sqlalchemy import Enum as SQLEnum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.domain.entities.enums import MuletillaSeverityEnum


class MuletillasWordUsage(Base):
    """Per-word count for a muletillas session. word is normalized (lowercased, trimmed)."""

    __tablename__ = "muletillas_word_usage"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    word: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    severity: Mapped[MuletillaSeverityEnum] = mapped_column(
        SQLEnum(MuletillaSeverityEnum, name="muletilla_severity_enum", create_type=False),
        nullable=False,
    )

    __table_args__ = (Index("ix_muletillas_word", "word"),)
