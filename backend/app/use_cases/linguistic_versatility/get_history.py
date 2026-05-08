import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.linguistic_versatility_session import LinguisticVersatilitySession


async def get_versatility_history(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[LinguisticVersatilitySession]:
    """Return all the user's versatility sessions, newest first."""
    result = await db.execute(
        select(LinguisticVersatilitySession)
        .where(LinguisticVersatilitySession.user_id == user_id)
        .order_by(LinguisticVersatilitySession.created_at.desc())
    )
    return list(result.scalars().all())
