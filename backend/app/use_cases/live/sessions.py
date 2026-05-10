from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import (
    ModuleEnum,
    SessionStatusEnum,
    StopReasonEnum,
)
from app.domain.entities.live_metrics import LiveMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User


class SessionNotFoundError(Exception):
    """Live session does not exist or does not belong to the calling user."""


class SessionNotActiveError(Exception):
    """Operation requires the live session to be in 'active' status."""


async def start_live_session(
    db: AsyncSession, user: User
) -> Session:
    """Open an active live session.

    Inserts only the sessions row with module='live', status='active',
    parent_id=NULL. live_metrics is intentionally not created yet because
    its stop_reason is unknown until finalize/abandon and its NOT NULL
    constraint forbids placeholder values; deferring keeps the model
    truthful.
    """

    started_at = datetime.now(timezone.utc)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.live,
        parent_id=None,
        started_at=started_at,
        ended_at=None,
        duration_ms=None,
        score=None,
        status=SessionStatusEnum.active,
    )
    db.add(session_row)
    await db.commit()
    await db.refresh(session_row)
    return session_row


async def _load_active_live_session(
    db: AsyncSession, user: User, session_id: UUID
) -> Session:
    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.live,
            )
        )
    ).scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        raise SessionNotFoundError(f"live session {session_id} not found")
    if session_row.status != SessionStatusEnum.active:
        raise SessionNotActiveError(
            f"live session {session_id} is {session_row.status.value}"
        )
    return session_row


async def _avg_completed_children_score(
    db: AsyncSession, parent_id: UUID
) -> int | None:
    """Average score of children that completed with a non-null score.

    Per the proposal: "Score de la live = promedio de hijos completados".
    Aborted children, or children that completed but had no scoring
    (e.g., all rounds unintelligible), are excluded. Returns None if
    nothing is averageable so the caller can persist NULL truthfully.
    """

    avg_value = (
        await db.execute(
            select(func.avg(Session.score)).where(
                Session.parent_id == parent_id,
                Session.status == SessionStatusEnum.completed,
                Session.score.is_not(None),
            )
        )
    ).scalar_one()
    if avg_value is None:
        return None
    return int(round(float(avg_value)))


async def finalize_live_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, LiveMetrics]:
    """Mark a live session completed.

    Sets ended_at, duration_ms, status='completed', score = avg of
    completed children's scores. Creates the live_metrics row with
    stop_reason='completed'. Use abandon for any other termination.
    """

    session_row = await _load_active_live_session(db, user, session_id)

    score = await _avg_completed_children_score(db, session_row.id)
    ended_at = datetime.now(timezone.utc)

    session_row.score = score
    session_row.ended_at = ended_at
    session_row.duration_ms = int(
        (ended_at - session_row.started_at).total_seconds() * 1000
    )
    session_row.status = SessionStatusEnum.completed

    metrics_row = LiveMetrics(
        session_id=session_row.id,
        stop_reason=StopReasonEnum.completed,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def abandon_live_session(
    db: AsyncSession,
    user: User,
    session_id: UUID,
    stop_reason: StopReasonEnum,
) -> tuple[Session, LiveMetrics]:
    """Mark a live session aborted with a non-completed stop_reason.

    Computes the same score as finalize over completed children so a
    partially-finished live still surfaces what got done. The status
    distinguishes aborted from completed; the stop_reason captures why.
    """

    if stop_reason == StopReasonEnum.completed:
        # Defensive: the schema is happy with 'completed' here but the
        # router's input schema rejects it. This guard exists in case a
        # future caller skips the schema layer.
        raise ValueError("stop_reason='completed' belongs to finalize, not abandon")

    session_row = await _load_active_live_session(db, user, session_id)

    score = await _avg_completed_children_score(db, session_row.id)
    ended_at = datetime.now(timezone.utc)

    session_row.score = score
    session_row.ended_at = ended_at
    session_row.duration_ms = int(
        (ended_at - session_row.started_at).total_seconds() * 1000
    )
    session_row.status = SessionStatusEnum.aborted

    metrics_row = LiveMetrics(
        session_id=session_row.id,
        stop_reason=stop_reason,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def list_live_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, int, str | None]]:
    """Timeline of live sessions for a user with a children count and the
    persisted stop_reason if any.

    Active live sessions appear here with children_count=0 (or whatever has
    been attached) and stop_reason=None. parent_id IS NULL is implicit:
    live is the root, never a child of another live in the current schema.
    """

    children_count_subq = (
        select(func.count(Session.id))
        .where(Session.parent_id == Session.id)  # placeholder, overridden below
        .correlate_except(Session)
    )

    # Build an explicit COUNT(children) per live session via a correlated
    # subquery. Doing it with a separate alias keeps the row select simple.
    from sqlalchemy.orm import aliased

    Child = aliased(Session)
    children_subq = (
        select(func.count(Child.id))
        .where(Child.parent_id == Session.id)
        .correlate(Session)
        .scalar_subquery()
    )

    query = (
        select(
            Session,
            children_subq.label("children_count"),
            LiveMetrics.stop_reason,
        )
        .outerjoin(LiveMetrics, LiveMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.live,
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return [
        (row[0], int(row[1]), row[2].value if row[2] is not None else None)
        for row in result.all()
    ]


async def get_live_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, LiveMetrics | None, list[Session]] | None:
    """Detail of one live session with its children.

    Returns None when the session does not exist or belongs to another user.
    Children are returned in started_at order so the UI can render the
    composition timeline directly.
    """

    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.live,
            )
        )
    ).scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_row = (
        await db.execute(
            select(LiveMetrics).where(LiveMetrics.session_id == session_id)
        )
    ).scalar_one_or_none()

    children = list(
        (
            await db.execute(
                select(Session)
                .where(Session.parent_id == session_id)
                .order_by(Session.started_at)
            )
        )
        .scalars()
        .all()
    )

    return session_row, metrics_row, children
