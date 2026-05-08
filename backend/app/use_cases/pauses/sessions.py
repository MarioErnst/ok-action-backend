from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.pause_session import PauseSession
from app.domain.entities.user import User


async def save_pause_session(
    data: dict,
    user: User,
    session: AsyncSession,
) -> PauseSession:
    metrics = data["pause_metrics"]
    pause_session = PauseSession(
        user_id=user.id,
        prompt_text=data["prompt_text"],
        duration_ms=data["duration_ms"],
        total_pauses=metrics["total_pauses"],
        total_pause_duration_ms=metrics["total_pause_duration_ms"],
        average_pause_ms=metrics["average_pause_ms"],
        longest_pause_ms=metrics["longest_pause_ms"],
        silence_ratio=metrics["silence_ratio"],
        classification=metrics["classification"],
        pauses=[pause for pause in metrics["pauses"]],
    )
    session.add(pause_session)
    await session.commit()
    await session.refresh(pause_session)
    return pause_session


async def list_pause_sessions(
    user: User,
    session: AsyncSession,
) -> list[PauseSession]:
    result = await session.execute(
        select(PauseSession)
        .where(PauseSession.user_id == user.id)
        .order_by(PauseSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_pause_session(
    session_id: str,
    user: User,
    session: AsyncSession,
) -> PauseSession | None:
    result = await session.execute(
        select(PauseSession).where(
            PauseSession.id == session_id,
            PauseSession.user_id == user.id,
        )
    )
    return result.scalar_one_or_none()
