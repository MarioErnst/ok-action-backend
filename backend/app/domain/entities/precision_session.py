import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class PrecisionSession(Base):
    __tablename__ = "precision_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="standalone")
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rounds: Mapped[list["PrecisionRound"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        # Apply Python-level defaults so they are available before flush/commit.
        kwargs.setdefault('id', uuid.uuid4())
        kwargs.setdefault('mode', 'standalone')
        kwargs.setdefault('completed_rounds', 0)
        kwargs.setdefault('status', 'active')
        kwargs.setdefault('created_at', datetime.now(timezone.utc))
        super().__init__(**kwargs)
