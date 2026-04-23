from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.phonation_session import PhonationSession
from app.domain.entities.exercise_result import ExerciseResult
from app.domain.entities.user import User


async def save_phonation_session(
    data: dict,
    user: User,
    session: AsyncSession,
) -> PhonationSession:
    phonation_session = PhonationSession(
        user_id=user.id,
        overall_score=data["overall_score"],
        avg_hz=data["avg_hz"],
        observations=data["observations"],
    )
    session.add(phonation_session)
    await session.flush()

    for exercise in data["exercises"]:
        session.add(ExerciseResult(
            session_id=phonation_session.id,
            exercise_id=exercise["exercise_id"],
            exercise_type=exercise["exercise_type"],
            avg_hz=exercise["avg_hz"],
            stability=exercise["stability"],
            breaks=exercise["breaks"],
            in_range=exercise["in_range"],
        ))

    await session.commit()
    await session.refresh(phonation_session)
    return phonation_session


async def list_phonation_sessions(
    user: User,
    session: AsyncSession,
) -> list[PhonationSession]:
    result = await session.execute(
        select(PhonationSession)
        .where(PhonationSession.user_id == user.id)
        .order_by(PhonationSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_phonation_session(
    session_id: str,
    user: User,
    session: AsyncSession,
) -> PhonationSession | None:
    result = await session.execute(
        select(PhonationSession)
        .options(selectinload(PhonationSession.exercise_results))
        .where(
            PhonationSession.id == session_id,
            PhonationSession.user_id == user.id,
        )
    )
    return result.scalar_one_or_none()
