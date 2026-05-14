"""Catalog access for the accentuation module.

Accentuation sessions iterate through every active phrase in the catalog,
so the only read use-case exposed today is a flat list. Keeping it in its
own file follows the single-responsibility convention used in pauses.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum
from app.domain.entities.prompt import Prompt


async def list_phrases(db: AsyncSession) -> list[Prompt]:
    """Return every active accentuation phrase, ordered by id for stability.

    The catalog is small and the frontend renders it in full, so we do not
    apply pagination. Ordering by id keeps the sequence deterministic across
    reloads — the UI is free to shuffle if needed.
    """

    result = await db.execute(
        select(Prompt)
        .where(Prompt.module == ModuleEnum.accentuation)
        .where(Prompt.is_active.is_(True))
        .order_by(Prompt.created_at, Prompt.id)
    )
    return list(result.scalars().all())


async def get_phrase_by_id(db: AsyncSession, prompt_id: UUID) -> Prompt | None:
    """Validate a prompt_id belongs to the active accentuation catalog.

    Used at the boundary of any endpoint that takes a prompt_id from the
    client. Returns None for unknown, inactive, or wrong-module ids.
    """

    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.module == ModuleEnum.accentuation,
            Prompt.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()
