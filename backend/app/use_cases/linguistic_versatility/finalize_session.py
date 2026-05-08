import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.linguistic_versatility_round import LinguisticVersatilityRound
from app.domain.entities.linguistic_versatility_session import LinguisticVersatilitySession


async def finalize_versatility_session(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> LinguisticVersatilitySession | None:
    """Mark a session completed and compute its overall_score.

    Overall score is the rounded mean of intelligible round scores. Rounds
    where the audio was unintelligible are excluded so a single bad recording
    doesn't drag the average down.

    Returns None when the session is missing (caller decides to 404).
    """
    session = await db.get(LinguisticVersatilitySession, session_id)
    if session is None:
        return None

    rounds_q = await db.execute(
        select(LinguisticVersatilityRound)
        .where(LinguisticVersatilityRound.session_id == session_id)
        .where(LinguisticVersatilityRound.audio_intelligible.is_(True))
    )
    scored_rounds = [
        r for r in rounds_q.scalars().all() if r.versatility_score is not None
    ]

    if scored_rounds:
        session.overall_score = round(
            sum(r.versatility_score for r in scored_rounds) / len(scored_rounds)
        )
    else:
        session.overall_score = None

    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return session
