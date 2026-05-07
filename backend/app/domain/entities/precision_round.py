import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class PrecisionRound(Base):
    __tablename__ = "precision_rounds"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("precision_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("precision_questions.id"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_duration_secs: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    directness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conciseness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    strengths: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    improvement_areas: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    noise_level: Mapped[str] = mapped_column(String(10), nullable=False, default="low")
    audio_intelligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["PrecisionSession"] = relationship(back_populates="rounds")

    def __init__(self, **kwargs):
        # Apply Python-level defaults so they are available before flush/commit.
        kwargs.setdefault('id', uuid.uuid4())
        kwargs.setdefault('noise_level', 'low')
        kwargs.setdefault('audio_intelligible', False)
        kwargs.setdefault('created_at', datetime.now(timezone.utc))
        super().__init__(**kwargs)
