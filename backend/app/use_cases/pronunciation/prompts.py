"""Catalog access for the pronunciation module.

The pronunciation UI groups phrases by difficulty (basico / intermedio /
avanzado). The list endpoint accepts an optional difficulty filter so the
frontend can fetch only the level the user picked, but also supports
returning the full catalog when no filter is supplied.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum
from app.domain.entities.prompt import Prompt


async def list_phrases(
    db: AsyncSession, difficulty: str | None = None
) -> list[Prompt]:
    """Return every active pronunciation phrase, optionally filtered by level.

    Ordering by created_at keeps the sequence stable. The frontend can pick
    its own randomisation if it wants variety per session.
    """

    query = (
        select(Prompt)
        .where(Prompt.module == ModuleEnum.pronunciation)
        .where(Prompt.is_active.is_(True))
    )
    if difficulty is not None:
        query = query.where(Prompt.difficulty == difficulty)
    query = query.order_by(Prompt.created_at, Prompt.id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_phrase_by_id(db: AsyncSession, prompt_id: UUID) -> Prompt | None:
    """Validate a prompt_id belongs to the active pronunciation catalog.

    Used at the boundary of any endpoint that takes a prompt_id from the
    client. Returns None for unknown, inactive, or wrong-module ids.
    """

    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.module == ModuleEnum.pronunciation,
            Prompt.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()
