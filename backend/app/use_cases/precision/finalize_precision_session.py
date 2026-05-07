import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.precision_round import PrecisionRound
from app.domain.entities.precision_session import PrecisionSession


async def finalize_precision_session(
    db: AsyncSession, session_id: uuid.UUID
) -> PrecisionSession:
    session = await db.get(PrecisionSession, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    rounds_result = await db.execute(
        select(PrecisionRound).where(
            PrecisionRound.session_id == session_id,
            PrecisionRound.audio_intelligible == True,
        )
    )
    evaluated_rounds = rounds_result.scalars().all()

    if evaluated_rounds:
        session.overall_score = sum(r.overall_score for r in evaluated_rounds) / len(evaluated_rounds)

    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return session
