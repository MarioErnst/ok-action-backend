import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class FacialExpressionSession(Base):
    __tablename__ = "facial_expression_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # dominant_* are nullable because a session with no events (cut short) has
    # no dominant emotion to report.
    dominant_emotion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dominant_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Per-emotion percentages of total session duration, e.g.
    # {"happy": 60, "neutral": 25, "surprise": 15}.
    emotion_distribution: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="facial_expression_sessions")
    events: Mapped[list["FacialExpressionEmotionEvent"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="FacialExpressionEmotionEvent.t_ms"
    )

    def __init__(self, **kwargs):
        # Apply Python-level defaults so they are available before flush/commit.
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        kwargs.setdefault("emotion_distribution", {})
        super().__init__(**kwargs)
