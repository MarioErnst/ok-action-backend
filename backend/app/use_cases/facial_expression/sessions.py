from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import (
    ModuleEnum,
    SessionStatusEnum,
    TopEmotionEnum,
)
from app.domain.entities.facial_expression_metrics import FacialExpressionMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.presentation.schemas.facial_expression import FacialExpressionSessionCreate
from app.use_cases.live.sessions import validate_parent_live_session


# Order matters: ties in the per-emotion percentages are broken in this order.
# Putting neutral last makes "tied with neutral" pick any expressive emotion
# instead of marking the session as neutral, which is the user-facing
# preference for the timeline card.
_EMOTION_ORDER: list[TopEmotionEnum] = [
    TopEmotionEnum.happy,
    TopEmotionEnum.sad,
    TopEmotionEnum.angry,
    TopEmotionEnum.surprised,
    TopEmotionEnum.fearful,
    TopEmotionEnum.disgusted,
    TopEmotionEnum.neutral,
]


def _derive_top_emotion(payload: FacialExpressionSessionCreate) -> TopEmotionEnum:
    metrics = payload.metrics
    pcts: dict[TopEmotionEnum, int] = {
        TopEmotionEnum.happy: metrics.happy_pct,
        TopEmotionEnum.sad: metrics.sad_pct,
        TopEmotionEnum.angry: metrics.angry_pct,
        TopEmotionEnum.surprised: metrics.surprised_pct,
        TopEmotionEnum.fearful: metrics.fearful_pct,
        TopEmotionEnum.disgusted: metrics.disgusted_pct,
        TopEmotionEnum.neutral: metrics.neutral_pct,
    }
    return max(_EMOTION_ORDER, key=lambda emotion: pcts[emotion])


def _derive_expressiveness_score(payload: FacialExpressionSessionCreate) -> int:
    """Inverse of neutral percentage: the more time spent non-neutral, the
    more expressive the user was. Single canonical formula so the server
    derives it; if a more nuanced metric is needed (variety, intensity peaks)
    change it here in one place."""

    return 100 - payload.metrics.neutral_pct


async def create_facial_expression_session(
    db: AsyncSession,
    user: User,
    payload: FacialExpressionSessionCreate,
) -> tuple[Session, FacialExpressionMetrics]:
    """Persist a completed facial expression session as one transaction.

    Inserts the root sessions row and the 1:1 facial_expression_metrics row.
    duration_ms is derived from the time range; expressiveness_score and
    top_emotion are derived from the seven percentages; the session score
    equals expressiveness_score because facial_expression has a single
    canonical scoring rule.
    """

    if payload.parent_id is not None:
        await validate_parent_live_session(db, user, payload.parent_id)

    duration_ms = int((payload.ended_at - payload.started_at).total_seconds() * 1000)
    top_emotion = _derive_top_emotion(payload)
    expressiveness = _derive_expressiveness_score(payload)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.facial_expression,
        parent_id=payload.parent_id,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_ms=duration_ms,
        score=expressiveness,
        status=SessionStatusEnum.completed,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = FacialExpressionMetrics(
        session_id=session_row.id,
        expressiveness_score=expressiveness,
        top_emotion=top_emotion,
        happy_pct=payload.metrics.happy_pct,
        sad_pct=payload.metrics.sad_pct,
        angry_pct=payload.metrics.angry_pct,
        surprised_pct=payload.metrics.surprised_pct,
        fearful_pct=payload.metrics.fearful_pct,
        disgusted_pct=payload.metrics.disgusted_pct,
        neutral_pct=payload.metrics.neutral_pct,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def list_facial_expression_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, FacialExpressionMetrics]]:
    """Timeline of completed standalone facial expression sessions for a user.

    parent_id IS NULL excludes sessions that belong to a live composition;
    those should be exposed through the live module's history.
    """

    query = (
        select(Session, FacialExpressionMetrics)
        .join(
            FacialExpressionMetrics,
            FacialExpressionMetrics.session_id == Session.id,
        )
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.facial_expression,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_facial_expression_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, FacialExpressionMetrics] | None:
    """Detail of one facial expression session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.module == ModuleEnum.facial_expression,
        )
    )
    session_row = session_result.scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_result = await db.execute(
        select(FacialExpressionMetrics).where(
            FacialExpressionMetrics.session_id == session_id
        )
    )
    metrics_row = metrics_result.scalar_one_or_none()
    if metrics_row is None:
        return None

    return session_row, metrics_row
