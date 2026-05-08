import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class LinguisticVersatilityRound(Base):
    """One evaluated audio response within a versatility session.

    For guided sessions, `question_id` and `question_text` reference the prompt
    the user was answering. For free sessions there is exactly one round per
    session and both fields stay NULL.

    `vocabulary_richness` is a 1..3 integer rather than a free string so
    histograms and analytics queries stay simple.
    """

    __tablename__ = "linguistic_versatility_rounds"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("linguistic_versatility_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("linguistic_versatility_questions.id"), nullable=True
    )
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    versatility_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vocabulary_richness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_intelligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["LinguisticVersatilitySession"] = relationship(back_populates="rounds")

    def __init__(self, **kwargs):
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("audio_intelligible", False)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)
