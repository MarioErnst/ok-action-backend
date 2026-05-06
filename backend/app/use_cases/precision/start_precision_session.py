import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.precision_question import PrecisionQuestion
from app.domain.entities.precision_round import PrecisionRound
from app.domain.entities.precision_session import PrecisionSession


async def start_precision_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    total_rounds: int = 5,
    mode: str = "standalone",
) -> tuple[PrecisionSession, list[PrecisionQuestion]]:
    # Get IDs of questions recently used by this user (last 3 sessions)
    recent_subq = (
        select(PrecisionRound.question_id)
        .join(PrecisionSession, PrecisionRound.session_id == PrecisionSession.id)
        .where(PrecisionSession.user_id == user_id)
        .order_by(PrecisionSession.created_at.desc())
        .limit(total_rounds * 3)
        .scalar_subquery()
    )

    questions_query = (
        select(PrecisionQuestion)
        .where(PrecisionQuestion.is_active == True)
        .where(PrecisionQuestion.id.notin_(recent_subq))
        .order_by(func.random())
        .limit(total_rounds)
    )
    result = await db.execute(questions_query)
    questions = result.scalars().all()

    # Fallback: if not enough non-recent questions, fill with any active questions
    if len(questions) < total_rounds:
        fallback_query = (
            select(PrecisionQuestion)
            .where(PrecisionQuestion.is_active == True)
            .order_by(func.random())
            .limit(total_rounds)
        )
        result = await db.execute(fallback_query)
        questions = result.scalars().all()

    session = PrecisionSession(
        id=uuid.uuid4(),
        user_id=user_id,
        mode=mode,
        total_rounds=total_rounds,
        completed_rounds=0,
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    return session, list(questions)
