import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class LinguisticVersatilityQuestion(Base):
    """Open-ended prompts shown in guided sessions of linguistic versatility.

    The set is curated to invite long-form answers (~30s) so Gemini has enough
    text to measure lexical diversity reliably.
    """

    __tablename__ = "linguistic_versatility_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty_level: Mapped[str] = mapped_column(String(20), nullable=False, default="basic")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __init__(self, **kwargs):
        # Apply Python-level defaults so they are available before flush/commit.
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("difficulty_level", "basic")
        kwargs.setdefault("is_active", True)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)
