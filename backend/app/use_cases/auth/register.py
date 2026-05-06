from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.domain.entities.user import User
from app.infrastructure.security.hashing import hash_password
from app.infrastructure.security.jwt import create_access_token


async def register_user(email: str, password: str, full_name: str, session: AsyncSession) -> dict | None:
    # Check if user already exists
    result = await session.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        return None

    # Create new user
    new_user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        is_active=True,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    access_token = create_access_token(subject=str(new_user.id))

    return {
        "access_token": access_token,
        "user": {
            "id": str(new_user.id),
            "email": new_user.email,
            "full_name": new_user.full_name,
            "is_active": new_user.is_active,
        },
    }
