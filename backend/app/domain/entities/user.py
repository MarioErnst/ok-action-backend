import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    role: Mapped["Role"] = relationship(back_populates="users")
    phonation_sessions: Mapped[list["PhonationSession"]] = relationship(back_populates="user")
    loudness_sessions: Mapped[list["LoudnessSession"]] = relationship(back_populates="user")
    loudness_presets: Mapped[list["LoudnessPreset"]] = relationship(back_populates="user")
    accentuation_sessions: Mapped[list["AccentuationSession"]] = relationship(back_populates="user")
    pronunciation_sessions: Mapped[list["PronunciationSession"]] = relationship(back_populates="user")
    muletillas_sessions: Mapped[list["MuletillasSession"]] = relationship(back_populates="user")
    live_sessions: Mapped[list["LiveSession"]] = relationship(back_populates="user")
    facial_expression_sessions: Mapped[list["FacialExpressionSession"]] = relationship(
        back_populates="user"
    )
    linguistic_versatility_sessions: Mapped[list["LinguisticVersatilitySession"]] = relationship(
        back_populates="user"
    )
