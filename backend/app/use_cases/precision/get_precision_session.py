import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.precision_session import PrecisionSession


async def get_precision_session(db: AsyncSession, session_id: uuid.UUID) -> PrecisionSession | None:
    result = await db.execute(
        select(PrecisionSession)
        .options(selectinload(PrecisionSession.rounds))
        .where(PrecisionSession.id == session_id)
    )
    return result.scalar_one_or_none()
