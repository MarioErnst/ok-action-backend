import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class FacialExpressionSession(Base):
    __tablename__ = "facial_expression_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    baseline_pucker: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    baseline_brow_down: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    baseline_lips_down: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="facial_expression_sessions")
    question_results: Mapped[list["FacialExpressionQuestionResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        # Apply Python-level defaults so they are available before flush/commit.
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)
