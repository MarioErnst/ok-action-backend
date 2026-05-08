import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.linguistic_versatility_question import LinguisticVersatilityQuestion
from app.domain.entities.linguistic_versatility_round import LinguisticVersatilityRound
from app.domain.entities.linguistic_versatility_session import LinguisticVersatilitySession


async def start_versatility_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    total_rounds: int = 3,
) -> tuple[LinguisticVersatilitySession, list[LinguisticVersatilityQuestion]]:
    """Open a guided session and pick the questions for it.

    Picks `total_rounds` random active questions, avoiding ones the user has
    answered in their last few sessions to keep the experience varied.
    Falls back to any active questions if not enough fresh ones exist.
    """
    recent_subq = (
        select(LinguisticVersatilityRound.question_id)
        .join(
            LinguisticVersatilitySession,
            LinguisticVersatilityRound.session_id == LinguisticVersatilitySession.id,
        )
        .where(LinguisticVersatilitySession.user_id == user_id)
        .order_by(LinguisticVersatilitySession.created_at.desc())
        .limit(total_rounds * 3)
        .scalar_subquery()
    )

    questions_query = (
        select(LinguisticVersatilityQuestion)
        .where(LinguisticVersatilityQuestion.is_active.is_(True))
        .where(LinguisticVersatilityQuestion.id.notin_(recent_subq))
        .order_by(func.random())
        .limit(total_rounds)
    )
    result = await db.execute(questions_query)
    questions = list(result.scalars().all())

    if len(questions) < total_rounds:
        # Not enough fresh questions — fall back to any active question.
        fallback_query = (
            select(LinguisticVersatilityQuestion)
            .where(LinguisticVersatilityQuestion.is_active.is_(True))
            .order_by(func.random())
            .limit(total_rounds)
        )
        result = await db.execute(fallback_query)
        questions = list(result.scalars().all())

    session = LinguisticVersatilitySession(
        user_id=user_id,
        mode="guided",
        total_rounds=len(questions),
    )
    db.add(session)
    await db.flush()
    return session, questions
