import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class PhraseEvaluation(Base):
    __tablename__ = "phrase_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accentuation_sessions.id", ondelete="CASCADE"), nullable=False
    )
    phrase_text: Mapped[str] = mapped_column(String(500), nullable=False)
    phrase_index: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    pronunciation_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    rhythm_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    intonation_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    stress_accuracy_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    specific_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["AccentuationSession"] = relationship(back_populates="phrase_evaluations")
