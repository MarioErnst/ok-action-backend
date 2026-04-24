import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class PronunciationSession(Base):
    __tablename__ = "pronunciation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    vowel_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    consonant_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    fluency_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    intelligibility_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    summary_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="pronunciation_sessions")
    phrase_pronunciations: Mapped[list["PhrasePronunciation"]] = relationship(
        back_populates="session"
    )
