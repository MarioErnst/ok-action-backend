import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.linguistic_versatility_session import LinguisticVersatilitySession


async def abandon_versatility_session(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> LinguisticVersatilitySession | None:
    """Mark a session as abandoned without computing a final score.

    Used when the user navigates away mid-session — keeps the partial rounds
    in history so the user can review what they did manage to record.
    Returns None when the session is missing.
    """
    session = await db.get(LinguisticVersatilitySession, session_id)
    if session is None:
        return None
    session.status = "abandoned"
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return session
