import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class PhrasePronunciation(Base):
    __tablename__ = "phrase_pronunciations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pronunciation_sessions.id", ondelete="CASCADE"), nullable=False
    )
    phrase_text: Mapped[str] = mapped_column(String(500), nullable=False)
    phrase_index: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    vowel_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    consonant_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    fluency_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    intelligibility_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    phoneme_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["PronunciationSession"] = relationship(back_populates="phrase_pronunciations")
