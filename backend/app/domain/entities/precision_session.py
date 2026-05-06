import uuid
from datetime import datetime, timezone
from typing import Optional

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

    def __init__(
        self,
        total_rounds: int = 0,
        user_id: Optional[uuid.UUID] = None,
        mode: str = "standalone",
        completed_rounds: int = 0,
        overall_score: Optional[float] = None,
        status: str = "active",
        id: Optional[uuid.UUID] = None,
        created_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ):
        self.id = id if id is not None else uuid.uuid4()
        self.user_id = user_id
        self.mode = mode
        self.total_rounds = total_rounds
        self.completed_rounds = completed_rounds
        self.overall_score = overall_score
        self.status = status
        self.created_at = created_at if created_at is not None else datetime.now(timezone.utc)
        self.completed_at = completed_at
