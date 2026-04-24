from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.accentuation_session import AccentuationSession
from app.domain.entities.phrase_evaluation import PhraseEvaluation
from app.domain.entities.user import User


async def save_accentuation_session(
    data: dict,
    user: User,
    session: AsyncSession,
) -> AccentuationSession:
    accentuation_session = AccentuationSession(
        user_id=user.id,
        overall_score=data["overall_score"],
        pronunciation_score=data["pronunciation_score"],
        rhythm_score=data["rhythm_score"],
        intonation_score=data["intonation_score"],
        stress_accuracy_score=data["stress_accuracy_score"],
        summary_feedback=data["summary_feedback"],
    )
    session.add(accentuation_session)
    await session.flush()
    await session.refresh(accentuation_session)

    for evaluation in data["evaluations"]:
        session.add(PhraseEvaluation(
            session_id=accentuation_session.id,
            phrase_text=evaluation["phrase_text"],
            phrase_index=evaluation["phrase_index"],
            overall_score=evaluation["overall_score"],
            pronunciation_score=evaluation["pronunciation_score"],
            rhythm_score=evaluation["rhythm_score"],
            intonation_score=evaluation["intonation_score"],
            stress_accuracy_score=evaluation["stress_accuracy_score"],
            feedback=evaluation["feedback"],
            specific_errors=evaluation["specific_errors"],
        ))

    await session.commit()
    await session.refresh(accentuation_session)
    return accentuation_session


async def list_accentuation_sessions(
    user: User,
    session: AsyncSession,
) -> list[AccentuationSession]:
    result = await session.execute(
        select(AccentuationSession)
        .where(AccentuationSession.user_id == user.id)
        .order_by(AccentuationSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_accentuation_session(
    session_id: str,
    user: User,
    session: AsyncSession,
) -> AccentuationSession | None:
    result = await session.execute(
        select(AccentuationSession)
        .options(selectinload(AccentuationSession.phrase_evaluations))
        .where(
            AccentuationSession.id == session_id,
            AccentuationSession.user_id == user.id,
        )
    )
    return result.scalar_one_or_none()
