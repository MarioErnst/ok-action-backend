from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.security.hashing import verify_password
from app.infrastructure.security.jwt import create_access_token


async def login_user(email: str, password: str, session: AsyncSession) -> dict | None:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        return None

    if not user.is_active:
        return None

    access_token = create_access_token(subject=str(user.id))

    return {
        "access_token": access_token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
        },
    }
