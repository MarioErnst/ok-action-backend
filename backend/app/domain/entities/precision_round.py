import uuid
from datetime import datetime, timezone
from typing import Optional

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

    def __init__(
        self,
        session_id: Optional[uuid.UUID] = None,
        question_id: Optional[uuid.UUID] = None,
        question_text: Optional[str] = None,
        audio_duration_secs: Optional[float] = None,
        transcript: Optional[str] = None,
        relevance_score: Optional[int] = None,
        directness_score: Optional[int] = None,
        conciseness_score: Optional[int] = None,
        overall_score: Optional[int] = None,
        feedback: Optional[str] = None,
        strengths: Optional[list] = None,
        improvement_areas: Optional[list] = None,
        noise_level: str = "low",
        audio_intelligible: bool = False,
        id: Optional[uuid.UUID] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = id if id is not None else uuid.uuid4()
        self.session_id = session_id
        self.question_id = question_id
        self.question_text = question_text
        self.audio_duration_secs = audio_duration_secs
        self.transcript = transcript
        self.relevance_score = relevance_score
        self.directness_score = directness_score
        self.conciseness_score = conciseness_score
        self.overall_score = overall_score
        self.feedback = feedback
        self.strengths = strengths
        self.improvement_areas = improvement_areas
        self.noise_level = noise_level
        self.audio_intelligible = audio_intelligible
        self.created_at = created_at if created_at is not None else datetime.now(timezone.utc)
