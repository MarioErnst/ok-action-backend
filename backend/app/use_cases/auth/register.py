from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.role import Role
from app.domain.entities.user import User
from app.infrastructure.security.hashing import hash_password
from app.infrastructure.security.jwt import create_access_token


async def register_user(
    full_name: str,
    email: str,
    password: str,
    session: AsyncSession,
) -> dict | None:
    normalized_email = email.strip().lower()

    existing = await session.execute(select(User).where(User.email == normalized_email))
    if existing.scalar_one_or_none():
        return None

    role_result = await session.execute(select(Role).where(Role.name == "user"))
    role = role_result.scalar_one_or_none()

    if not role:
        role = Role(
            name="user",
            description="Usuario estandar con acceso basico a la plataforma",
        )
        session.add(role)
        await session.flush()

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role_id=role.id,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

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
