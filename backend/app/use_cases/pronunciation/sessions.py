from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.phrase_pronunciation import PhrasePronunciation
from app.domain.entities.pronunciation_session import PronunciationSession
from app.domain.entities.user import User


async def save_pronunciation_session(
    data: dict,
    user: User,
    session: AsyncSession,
) -> PronunciationSession:
    pronunciation_session = PronunciationSession(
        user_id=user.id,
        level=data["level"],
        overall_score=data["overall_score"],
        vowel_score=data["vowel_score"],
        consonant_score=data["consonant_score"],
        fluency_score=data["fluency_score"],
        intelligibility_score=data["intelligibility_score"],
        summary_feedback=data["summary_feedback"],
    )
    session.add(pronunciation_session)
    await session.flush()
    await session.refresh(pronunciation_session)

    for evaluation in data["evaluations"]:
        session.add(PhrasePronunciation(
            session_id=pronunciation_session.id,
            phrase_text=evaluation["phrase_text"],
            phrase_index=evaluation["phrase_index"],
            overall_score=evaluation["overall_score"],
            vowel_score=evaluation["vowel_score"],
            consonant_score=evaluation["consonant_score"],
            fluency_score=evaluation["fluency_score"],
            intelligibility_score=evaluation["intelligibility_score"],
            feedback=evaluation["feedback"],
            phoneme_errors=evaluation["phoneme_errors"],
        ))

    await session.commit()
    await session.refresh(pronunciation_session)
    return pronunciation_session


async def list_pronunciation_sessions(
    user: User,
    session: AsyncSession,
) -> list[PronunciationSession]:
    result = await session.execute(
        select(PronunciationSession)
        .where(PronunciationSession.user_id == user.id)
        .order_by(PronunciationSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_pronunciation_session(
    session_id: str,
    user: User,
    session: AsyncSession,
) -> PronunciationSession | None:
    result = await session.execute(
        select(PronunciationSession)
        .options(selectinload(PronunciationSession.phrase_pronunciations))
        .where(
            PronunciationSession.id == session_id,
            PronunciationSession.user_id == user.id,
        )
    )
    return result.scalar_one_or_none()
