import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class MuletillasSession(Base):
    __tablename__ = "muletillas_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    overall_score: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    fluency_score: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    muletillas_score: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    total_muletillas_count: Mapped[int] = mapped_column(Integer, nullable=False)
    muletillas_per_minute: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[str] = mapped_column(Text, nullable=False)
    improvement_areas: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="muletillas_sessions")
    muletillas_detected: Mapped[list["PhraseMuletillas"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class PhraseMuletillas(Base):
    __tablename__ = "phrase_muletillas"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("muletillas_sessions.id", ondelete="CASCADE"), nullable=False
    )
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)

    session: Mapped["MuletillasSession"] = relationship(back_populates="muletillas_detected")
