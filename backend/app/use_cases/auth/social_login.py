from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.domain.entities.user import User
from app.infrastructure.security.jwt import create_access_token


async def social_login_user(email: str, full_name: str, provider: str, session: AsyncSession) -> dict | None:
    # Check if user already exists
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # Create new user for social login (no password)
        user = User(
            email=email,
            password_hash="social",  # Or NULL if column allows, but "social" is a placeholder
            full_name=full_name,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif not user.is_active:
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
