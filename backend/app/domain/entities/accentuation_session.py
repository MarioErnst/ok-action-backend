import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class AccentuationSession(Base):
    __tablename__ = "accentuation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    pronunciation_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    rhythm_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    intonation_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    stress_accuracy_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    summary_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="accentuation_sessions")
    phrase_evaluations: Mapped[list["PhraseEvaluation"]] = relationship(back_populates="session")
