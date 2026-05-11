from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.loudness_preset import LoudnessPreset
from app.domain.entities.user import User
from app.presentation.schemas.loudness import (
    LoudnessPresetCreate,
    LoudnessPresetUpdate,
)


class PresetReferencedError(Exception):
    """Raised when trying to delete a preset that is referenced by a session."""


async def list_presets(db: AsyncSession, user: User) -> list[LoudnessPreset]:
    """Return system-wide presets plus the ones owned by the user.

    Defaults are surfaced first so the UI can highlight them; ties break by
    label for a stable visual order.
    """

    query = (
        select(LoudnessPreset)
        .where(
            or_(
                LoudnessPreset.user_id.is_(None),
                LoudnessPreset.user_id == user.id,
            )
        )
        .order_by(LoudnessPreset.is_default.desc(), LoudnessPreset.label)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_preset(
    db: AsyncSession, user: User, payload: LoudnessPresetCreate
) -> LoudnessPreset:
    """Create a custom preset owned by the user. is_default is forced False
    because only seed-time globals carry that flag."""

    preset = LoudnessPreset(
        user_id=user.id,
        is_default=False,
        label=payload.label,
        description=payload.description,
        silence_offset_db=payload.silence_offset_db,
        low_offset_db=payload.low_offset_db,
        optimal_offset_db=payload.optimal_offset_db,
        clip_threshold_db=payload.clip_threshold_db,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def update_preset(
    db: AsyncSession,
    user: User,
    preset_id: UUID,
    payload: LoudnessPresetUpdate,
) -> LoudnessPreset | None:
    """Update fields of a user-owned preset. Globals (user_id IS NULL) are not
    editable; the query already filters by user_id so they return None."""

    result = await db.execute(
        select(LoudnessPreset).where(
            LoudnessPreset.id == preset_id,
            LoudnessPreset.user_id == user.id,
        )
    )
    preset = result.scalar_one_or_none()
    if preset is None:
        return None

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(preset, field, value)

    await db.commit()
    await db.refresh(preset)
    return preset


async def delete_preset(
    db: AsyncSession, user: User, preset_id: UUID
) -> bool:
    """Delete a user-owned preset. Globals are not deletable; missing or other
    users' presets return False. Raises PresetReferencedError if the FK
    RESTRICT from loudness_metrics blocks the delete."""

    result = await db.execute(
        select(LoudnessPreset).where(
            LoudnessPreset.id == preset_id,
            LoudnessPreset.user_id == user.id,
        )
    )
    preset = result.scalar_one_or_none()
    if preset is None:
        return False

    await db.delete(preset)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise PresetReferencedError(str(exc)) from exc
    return True
