import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class PrecisionQuestion(Base):
    __tablename__ = "precision_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty_level: Mapped[str] = mapped_column(String(20), nullable=False, default="basic")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __init__(
        self,
        text: Optional[str] = None,
        category: Optional[str] = None,
        difficulty_level: str = "basic",
        is_active: bool = True,
        id: Optional[uuid.UUID] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = id if id is not None else uuid.uuid4()
        self.text = text
        self.category = category
        self.difficulty_level = difficulty_level
        self.is_active = is_active
        self.created_at = created_at if created_at is not None else datetime.now(timezone.utc)
