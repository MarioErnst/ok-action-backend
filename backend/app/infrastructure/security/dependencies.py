import logging

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.jwt import decode_access_token

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def authenticate_ws(token: str, db: AsyncSession) -> User | None:
    """
    Validates a JWT token from a WebSocket query parameter and returns the active user.

    Returns None instead of raising exceptions so the WebSocket handler can close
    the connection with a specific close code rather than an unhandled error.
    """
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    except Exception as exc:
        logger.error("DB error during WS auth: %s", exc)
        return None
    if not user or not user.is_active:
        return None
    return user


async def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User:
    payload = decode_access_token(token.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")

    return user
