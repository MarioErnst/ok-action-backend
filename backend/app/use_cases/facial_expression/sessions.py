# Business logic for facial expression session CRUD: documentacion/modulos/expresion-facial.md
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.facial_expression_session import FacialExpressionSession
from app.domain.entities.facial_expression_emotion_event import (
    FacialExpressionEmotionEvent,
)
from app.domain.entities.user import User
from app.use_cases.facial_expression.distribution import compute_distribution


async def save_facial_expression_session(
    data: dict,
    user: User,
    session: AsyncSession,
) -> FacialExpressionSession:
    """Persist a session and its emotion events, computing the distribution server-side.

    Args:
        data: {"duration_ms": int, "events": [{"t_ms": int, "emotion": str, "gestures": dict}]}
        user: authenticated User entity.
        session: async database session.

    Returns:
        Persisted FacialExpressionSession instance.
    """
    duration_ms = data["duration_ms"]
    events = data.get("events", [])

    distribution, dominant_emotion, dominant_percentage = compute_distribution(
        duration_ms, events
    )

    facial_session = FacialExpressionSession(
        user_id=user.id,
        duration_ms=duration_ms,
        dominant_emotion=dominant_emotion,
        dominant_percentage=dominant_percentage,
        emotion_distribution=distribution,
    )
    session.add(facial_session)
    await session.flush()

    for ev in events:
        session.add(
            FacialExpressionEmotionEvent(
                session_id=facial_session.id,
                t_ms=ev["t_ms"],
                emotion=ev["emotion"],
                gestures=ev.get("gestures", {}),
            )
        )

    await session.commit()
    await session.refresh(facial_session)
    return facial_session


async def list_facial_expression_sessions(
    user: User,
    session: AsyncSession,
) -> list[FacialExpressionSession]:
    """Return all facial expression sessions for a user, newest first."""
    result = await session.execute(
        select(FacialExpressionSession)
        .where(FacialExpressionSession.user_id == user.id)
        .order_by(FacialExpressionSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_facial_expression_session(
    session_id: str,
    user: User,
    session: AsyncSession,
) -> FacialExpressionSession | None:
    """Return a single session with its events, or None if not found or not owned."""
    result = await session.execute(
        select(FacialExpressionSession)
        .options(selectinload(FacialExpressionSession.events))
        .where(
            FacialExpressionSession.id == session_id,
            FacialExpressionSession.user_id == user.id,
        )
    )
    return result.scalar_one_or_none()
