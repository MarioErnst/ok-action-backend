import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.linguistic_versatility_session import LinguisticVersatilitySession


async def get_versatility_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> LinguisticVersatilitySession | None:
    """Return the session with its rounds eagerly loaded, enforcing ownership.

    Returns None when the session is missing OR belongs to a different user —
    the caller cannot distinguish the two and that's intentional, so we don't
    leak the existence of other users' sessions.
    """
    result = await db.execute(
        select(LinguisticVersatilitySession)
        .options(selectinload(LinguisticVersatilitySession.rounds))
        .where(
            LinguisticVersatilitySession.id == session_id,
            LinguisticVersatilitySession.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()
