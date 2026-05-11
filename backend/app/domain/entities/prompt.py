from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CHAR, DateTime, Enum as SQLEnum, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.domain.entities.enums import ModuleEnum


class Prompt(Base):
    """Unified catalog of questions and phrases for every module."""

    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    module: Mapped[ModuleEnum] = mapped_column(
        SQLEnum(ModuleEnum, name="module_enum", create_type=False), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="basic")
    language: Mapped[str] = mapped_column(CHAR(2), nullable=False, default="es")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("module", "text", name="uq_prompts_module_text"),
        Index("ix_prompts_module_active_difficulty", "module", "is_active", "difficulty"),
    )
