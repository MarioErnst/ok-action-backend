# Business logic for the loudness module: documentacion/modulos/volumen.md
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.loudness_preset import LoudnessPreset
from app.domain.entities.user import User


async def list_presets(user: User, session: AsyncSession) -> list[LoudnessPreset]:
    result = await session.execute(
        select(LoudnessPreset).where(
            or_(
                LoudnessPreset.user_id.is_(None),
                LoudnessPreset.user_id == user.id,
            )
        ).order_by(LoudnessPreset.is_default.desc(), LoudnessPreset.label)
    )
    return list(result.scalars().all())


async def create_preset(
    data: dict, user: User, session: AsyncSession
) -> LoudnessPreset:
    preset = LoudnessPreset(
        user_id=user.id,
        is_default=False,
        **data,
    )
    session.add(preset)
    await session.commit()
    await session.refresh(preset)
    return preset


async def update_preset(
    preset_id: str, data: dict, user: User, session: AsyncSession
) -> LoudnessPreset | None:
    result = await session.execute(
        select(LoudnessPreset).where(
            LoudnessPreset.id == preset_id,
            LoudnessPreset.user_id == user.id,
        )
    )
    preset = result.scalar_one_or_none()
    if not preset:
        return None

    for key, value in data.items():
        if value is not None:
            setattr(preset, key, value)

    await session.commit()
    await session.refresh(preset)
    return preset


async def delete_preset(
    preset_id: str, user: User, session: AsyncSession
) -> bool:
    result = await session.execute(
        select(LoudnessPreset).where(
            LoudnessPreset.id == preset_id,
            LoudnessPreset.user_id == user.id,
        )
    )
    preset = result.scalar_one_or_none()
    if not preset:
        return False

    await session.delete(preset)
    await session.commit()
    return True
