import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class FacialExpressionEmotionEvent(Base):
    """One event per detected change of dominant emotion within a session.

    gestures captures the active gestures and their intensities (0.0–1.0)
    at the instant the dominant emotion changed, so analytics can correlate
    gesture activity with emotional transitions.
    """

    __tablename__ = "facial_expression_emotion_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facial_expression_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    t_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    emotion: Mapped[str] = mapped_column(String(20), nullable=False)
    gestures: Mapped[dict] = mapped_column(JSONB, nullable=False)

    session: Mapped["FacialExpressionSession"] = relationship(back_populates="events")

    def __init__(self, **kwargs):
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("gestures", {})
        super().__init__(**kwargs)
