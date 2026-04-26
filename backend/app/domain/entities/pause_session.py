import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class PauseSession(Base):
    __tablename__ = "pause_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    prompt_text: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    total_pauses: Mapped[int] = mapped_column(Integer, nullable=False)
    total_pause_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    average_pause_ms: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    longest_pause_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    silence_ratio: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    classification: Mapped[str] = mapped_column(String(50), nullable=False)
    pauses: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="pause_sessions")
