import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.live_session import LiveSession
from app.domain.entities.user import User
from app.use_cases.live_session.session_manager import LiveSessionState

logger = logging.getLogger(__name__)


async def save_live_session(
    state: LiveSessionState,
    user: User,
    db: AsyncSession,
) -> LiveSession:
    """
    Persists the live session to the database at close time.
    Not called during the session to avoid N writes per cycle.
    """
    record = LiveSession(
        user_id=user.id,
        selected_dims=state.selected_dims,
        analyses=state.analyses,
        overall_score=state.average_overall(),
        total_errors=state.accumulated_errors,
        duration_seconds=state.elapsed_seconds(),
        stop_reason=state.stop_reason or "user_ended",
    )
    db.add(record)
    try:
        await db.commit()
        await db.refresh(record)
    except SQLAlchemyError as exc:
        logger.error("Failed to save live session for user %s: %s", user.id, exc)
        await db.rollback()
        raise
    return record


async def list_live_sessions(user: User, db: AsyncSession) -> list[LiveSession]:
    """Returns all live sessions for the given user, newest first."""
    result = await db.execute(
        select(LiveSession)
        .where(LiveSession.user_id == user.id)
        .order_by(LiveSession.created_at.desc())
    )
    return list(result.scalars().all())
