import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class LinguisticVersatilitySession(Base):
    """A linguistic versatility analysis session — guided or free.

    Both modes share the same table so history queries can return them in one
    place. `mode` is one of {"guided", "free"}.
    """

    __tablename__ = "linguistic_versatility_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="guided")
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="linguistic_versatility_sessions")
    rounds: Mapped[list["LinguisticVersatilityRound"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="LinguisticVersatilityRound.created_at",
    )

    def __init__(self, **kwargs):
        # Apply Python-level defaults so they are available before flush/commit.
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("mode", "guided")
        kwargs.setdefault("completed_rounds", 0)
        kwargs.setdefault("status", "active")
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)
