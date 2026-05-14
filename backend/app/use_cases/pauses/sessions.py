from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.pause_metrics import PauseMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.presentation.schemas.pauses import PauseSessionCreate
from app.use_cases.live.sessions import validate_parent_live_session
from app.use_cases.pauses.prompts import get_prompt_by_id


class PausePromptNotAvailableError(ValueError):
    """Raised when prompt_id in the payload is unknown, inactive, or not
    a pauses prompt. The router maps it to 422.
    """


async def create_pause_session(
    db: AsyncSession,
    user: User,
    payload: PauseSessionCreate,
) -> tuple[Session, PauseMetrics]:
    """Persist a completed pauses session as one transaction.

    Inserts the root sessions row and the 1:1 pause_metrics row. duration_ms
    is derived server-side from the time range. Score comes from the client
    because pauses scoring is a composite of count, total duration and
    silence ratio that the frontend computes. The optional prompt_id is
    validated against the catalog before persisting so a client cannot link
    a pauses session to a prompt from another module.
    """

    if payload.parent_id is not None:
        await validate_parent_live_session(db, user, payload.parent_id)

    prompt_id = payload.metrics.prompt_id
    if prompt_id is not None:
        prompt_row = await get_prompt_by_id(db, prompt_id)
        if prompt_row is None:
            raise PausePromptNotAvailableError(
                f"prompt {prompt_id} no está disponible para pausas"
            )

    duration_ms = int((payload.ended_at - payload.started_at).total_seconds() * 1000)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.pauses,
        parent_id=payload.parent_id,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_ms=duration_ms,
        score=payload.score,
        status=SessionStatusEnum.completed,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = PauseMetrics(
        session_id=session_row.id,
        pauses_count=payload.metrics.pauses_count,
        total_pause_ms=payload.metrics.total_pause_ms,
        longest_pause_ms=payload.metrics.longest_pause_ms,
        silence_pct=payload.metrics.silence_pct,
        prompt_id=prompt_id,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def list_pause_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, PauseMetrics]]:
    """Timeline of completed standalone pauses sessions for a user.

    parent_id IS NULL excludes sessions that belong to a live composition;
    those should be exposed through the live module's history.
    """

    query = (
        select(Session, PauseMetrics)
        .join(PauseMetrics, PauseMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.pauses,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_pause_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, PauseMetrics] | None:
    """Detail of one pauses session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.module == ModuleEnum.pauses,
        )
    )
    session_row = session_result.scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_result = await db.execute(
        select(PauseMetrics).where(PauseMetrics.session_id == session_id)
    )
    metrics_row = metrics_result.scalar_one_or_none()
    if metrics_row is None:
        return None

    return session_row, metrics_row
