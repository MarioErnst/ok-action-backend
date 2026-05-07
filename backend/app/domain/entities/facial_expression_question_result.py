import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class FacialExpressionQuestionResult(Base):
    __tablename__ = "facial_expression_question_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facial_expression_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(String(50), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # Raw frame data: list of {t, pk, bd, ld} dicts captured at 15fps
    frames: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    pucker_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brow_down_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lips_down_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["FacialExpressionSession"] = relationship(back_populates="question_results")

    def __init__(self, **kwargs):
        # Apply Python-level defaults so they are available before flush/commit.
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)
