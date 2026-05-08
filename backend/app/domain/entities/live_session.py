import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class LiveSession(Base):
    __tablename__ = "live_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    selected_dims: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    analyses: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    overall_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stop_reason: Mapped[str] = mapped_column(String(20), nullable=False)
    # Linguistic versatility analysis Gemini produces at session close when
    # the 'lex' dimension was selected. NULL when lex was not requested.
    lex_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="live_sessions")
