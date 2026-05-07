import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.precision_session import PrecisionSession


async def abandon_precision_session(db: AsyncSession, session_id: uuid.UUID) -> None:
    session = await db.get(PrecisionSession, session_id)
    if session and session.status == "active":
        session.status = "abandoned"
        await db.flush()
