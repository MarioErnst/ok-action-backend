import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.precision_session import PrecisionSession


async def get_precision_history(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 20
) -> list[PrecisionSession]:
    result = await db.execute(
        select(PrecisionSession)
        .where(PrecisionSession.user_id == user_id)
        .where(PrecisionSession.status == "completed")
        .order_by(PrecisionSession.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
