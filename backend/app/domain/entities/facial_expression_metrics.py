from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Enum as SQLEnum, ForeignKey, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.domain.entities.enums import TopEmotionEnum


class FacialExpressionMetrics(Base):
    __tablename__ = "facial_expression_metrics"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    expressiveness_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    top_emotion: Mapped[TopEmotionEnum] = mapped_column(
        SQLEnum(TopEmotionEnum, name="top_emotion_enum", create_type=False), nullable=False
    )
    happy_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sad_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    angry_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    surprised_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fearful_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    disgusted_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    neutral_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "expressiveness_score BETWEEN 0 AND 100",
            name="ck_facial_expressiveness_score",
        ),
        CheckConstraint("happy_pct BETWEEN 0 AND 100", name="ck_facial_happy_pct"),
        CheckConstraint("sad_pct BETWEEN 0 AND 100", name="ck_facial_sad_pct"),
        CheckConstraint("angry_pct BETWEEN 0 AND 100", name="ck_facial_angry_pct"),
        CheckConstraint("surprised_pct BETWEEN 0 AND 100", name="ck_facial_surprised_pct"),
        CheckConstraint("fearful_pct BETWEEN 0 AND 100", name="ck_facial_fearful_pct"),
        CheckConstraint("disgusted_pct BETWEEN 0 AND 100", name="ck_facial_disgusted_pct"),
        CheckConstraint("neutral_pct BETWEEN 0 AND 100", name="ck_facial_neutral_pct"),
        CheckConstraint(
            "happy_pct + sad_pct + angry_pct + surprised_pct + fearful_pct + disgusted_pct + neutral_pct = 100",
            name="ck_facial_pct_total",
        ),
    )
