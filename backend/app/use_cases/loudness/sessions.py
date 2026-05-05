from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.loudness_session import LoudnessSession
from app.domain.entities.user import User


async def save_loudness_session(
    data: dict, user: User, session: AsyncSession
) -> LoudnessSession:
    loudness_session = LoudnessSession(
        user_id=user.id,
        preset_id=data["preset_id"],
        duration_ms=data["duration_ms"],
        optimal_percent=data["optimal_percent"],
        peak_db=data["peak_db"],
        band_time_ms=data["band_time_ms"],
    )
    session.add(loudness_session)
    await session.commit()
    await session.refresh(loudness_session)
    return loudness_session


async def list_loudness_sessions(
    user: User, session: AsyncSession
) -> list[LoudnessSession]:
    result = await session.execute(
        select(LoudnessSession)
        .where(LoudnessSession.user_id == user.id)
        .order_by(LoudnessSession.created_at.desc())
    )
    return list(result.scalars().all())
