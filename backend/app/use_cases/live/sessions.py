from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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


class InvalidParentLiveError(Exception):
    """parent_id does not reference an active live session owned by the user.

    Raised by component modules (phonation, fluency, etc.) when a client
    tries to persist a child session whose parent_id points at something
    that is not a live, is not active, or belongs to another user.
    """


async def validate_parent_live_session(
    db: AsyncSession, user: User, parent_id: UUID
) -> None:
    """Verify parent_id references a live session the caller can attach to.

    Component modules call this before inserting a session with parent_id
    set. The single query checks all four invariants at once: the row
    exists, module='live', status='active', and user_id matches. Anything
    else raises InvalidParentLiveError so the router can map it to 422.
    """

    parent = (
        await db.execute(
            select(Session).where(
                Session.id == parent_id,
                Session.module == ModuleEnum.live,
                Session.status == SessionStatusEnum.active,
                Session.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if parent is None:
        raise InvalidParentLiveError(
            f"parent_id {parent_id} is not an active live session owned by you"
        )


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


_AUTO_STOP_REASONS = frozenset(
    {StopReasonEnum.auto_stop_strikes, StopReasonEnum.auto_stop_emotion}
)


async def finalize_live_session(
    db: AsyncSession,
    user: User,
    session_id: UUID,
    auto_stop_reason: StopReasonEnum | None = None,
) -> tuple[Session, LiveMetrics]:
    """Close a live session and persist its metrics row.

    Default behavior (auto_stop_reason=None) marks the session as
    completed and writes stop_reason='completed'.

    When the client invokes finalize because the strike system or the
    sustained-emotion watchdog triggered, it passes the corresponding
    auto_stop_reason ('auto_stop_strikes' or 'auto_stop_emotion'). In that
    case the session is marked aborted (the strike system cut it short, it
    was not a natural completion) and stop_reason records why. Score is
    still computed over completed children so any partial children stay
    visible.
    """

    if auto_stop_reason is not None and auto_stop_reason not in _AUTO_STOP_REASONS:
        raise ValueError(
            f"auto_stop_reason must be one of {sorted(r.value for r in _AUTO_STOP_REASONS)}"
        )

    session_row = await _load_active_live_session(db, user, session_id)

    score = await _avg_completed_children_score(db, session_row.id)
    ended_at = datetime.now(timezone.utc)

    session_row.score = score
    session_row.ended_at = ended_at
    session_row.duration_ms = int(
        (ended_at - session_row.started_at).total_seconds() * 1000
    )

    if auto_stop_reason is None:
        session_row.status = SessionStatusEnum.completed
        persisted_reason = StopReasonEnum.completed
    else:
        session_row.status = SessionStatusEnum.aborted
        persisted_reason = auto_stop_reason

    metrics_row = LiveMetrics(
        session_id=session_row.id,
        stop_reason=persisted_reason,
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

    # Correlated COUNT(children) per live session via an aliased Session.
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
