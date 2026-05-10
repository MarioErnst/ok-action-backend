from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.consistency_metrics import ConsistencyMetrics
from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.session import Session
from app.domain.entities.user import User


def _safe_int(value: object, default: int = 0) -> int:
    """Coerce Gemini values that should be ints. Returns default on failure
    so a single bad field does not poison the whole session."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp_pct(value: int) -> int:
    """Clamp to [0, 100] so an out-of-range Gemini value does not violate
    the SMALLINT CHECK constraint at insert time."""

    return max(0, min(100, value))


def _derive_volatility_score(volatility_events: list) -> int:
    """Translate the count of volatility events into a 0-100 score.

    Each event subtracts 20 points; 5 or more events bottoms out at 0. Single
    canonical formula on the server so the meaning is consistent. If we ever
    want a finer-grained measure, change it here in one place.
    """

    return max(0, 100 - len(volatility_events) * 20)


def _aggregate_analysis(analysis: dict) -> tuple[int, int, int, int]:
    """Reduce the single Gemini analysis into the four persisted values.

    Returns (overall_score, consistency_score, volatility_score, active_pct).
    All four are SMALLINT 0-100 columns; the helper clamps so a stray Gemini
    out-of-range value does not blow up the insert.
    """

    overall = _clamp_pct(_safe_int(analysis.get("score"), 0))
    consistency = overall
    volatility = _derive_volatility_score(analysis.get("volatility_events") or [])
    active = _clamp_pct(_safe_int(analysis.get("active_pct"), 0))
    return overall, consistency, volatility, active


async def persist_consistency_session(
    db: AsyncSession,
    user: User,
    started_at: datetime,
    ended_at: datetime,
    status: SessionStatusEnum,
    analysis: dict | None,
    parent_id: UUID | None = None,
) -> tuple[Session, ConsistencyMetrics] | None:
    """Insert one sessions row + 1:1 consistency_metrics row at WS close.

    parent_id is taken from the WS start message and validated by the
    router before this call (authentication and validation are router
    concerns; the use_case trusts the value here).

    Returns None when there was no Gemini analysis to persist (audio buffer
    was below the minimum or the Gemini call failed). The caller should
    treat None as "nothing to persist", not as an error.
    """

    if analysis is None:
        return None

    overall, consistency, volatility, active = _aggregate_analysis(analysis)
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.consistency,
        parent_id=parent_id,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        score=overall,
        status=status,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = ConsistencyMetrics(
        session_id=session_row.id,
        consistency_score=consistency,
        volatility_score=volatility,
        active_pct=active,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def list_consistency_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, ConsistencyMetrics]]:
    """Timeline of completed/aborted standalone consistency sessions for a user.

    parent_id IS NULL excludes sessions that belong to a live composition.
    Active sessions never appear: consistency only persists at WS close.
    """

    query = (
        select(Session, ConsistencyMetrics)
        .join(ConsistencyMetrics, ConsistencyMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.consistency,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_consistency_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, ConsistencyMetrics] | None:
    """Detail of one consistency session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.consistency,
            )
        )
    ).scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_row = (
        await db.execute(
            select(ConsistencyMetrics).where(
                ConsistencyMetrics.session_id == session_id
            )
        )
    ).scalar_one_or_none()
    if metrics_row is None:
        return None

    return session_row, metrics_row
