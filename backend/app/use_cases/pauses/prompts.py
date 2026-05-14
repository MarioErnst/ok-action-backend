"""Catalog access for the pauses module.

Pauses does not evaluate audio in the backend (the frontend runs the whole
voiceSegmentation pipeline), so the only use-case-level interaction with
the prompts catalog is exposing one prompt at session start. Keeping this
in its own file follows the single-responsibility convention used for the
rest of the module.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum
from app.domain.entities.prompt import Prompt


class NoPausePromptsError(RuntimeError):
    """Raised when the prompts catalog has no active pauses prompts.

    The router maps this to 503 so the client can show a "catalogue not
    seeded" error instead of an opaque 500.
    """


async def get_random_prompt(db: AsyncSession) -> Prompt:
    """Return one active pauses prompt picked randomly from the catalog.

    Returns the whole Prompt row (not just text) so the caller can persist
    the prompt_id with the session and show the same text in the recording
    UI without a second round-trip.
    """

    result = await db.execute(
        select(Prompt)
        .where(Prompt.module == ModuleEnum.pauses)
        .where(Prompt.is_active.is_(True))
        .order_by(func.random())
        .limit(1)
    )
    prompt_row = result.scalar_one_or_none()
    if prompt_row is None:
        raise NoPausePromptsError("No hay prompts disponibles para pausas")
    return prompt_row


async def get_prompt_by_id(db: AsyncSession, prompt_id: UUID) -> Prompt | None:
    """Return one active pauses prompt by id.

    Used by the session-create flow to validate the prompt_id the client
    sends. Returns None for unknown id, inactive prompt, or wrong module.
    """

    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.module == ModuleEnum.pauses,
            Prompt.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()
