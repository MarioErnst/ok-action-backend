from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.fluency_metrics import FluencyMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User


def _safe_int(value: object, default: int = 0) -> int:
    """Coerce Gemini values that should be ints but may arrive as floats or
    strings. Returns default on any failure so a single bad analysis does not
    poison the whole aggregate."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _aggregate_analyses(analyses: list[dict]) -> tuple[int, int, int, Decimal]:
    """Reduce per-chunk Gemini analyses into the four persisted metrics.

    Returns (overall_score, fluency_score, stuck_events_count, wpm). Mean is
    computed across all analyses (intelligible or not) since the WS protocol
    already filters out non-analyses before they reach this list.
    stuck_events_count keeps the broad definition the OLD WS warning logic
    used: stuck events + repetitions + restarts + long blocks.
    """

    if not analyses:
        return 0, 0, 0, Decimal("0")

    overall_scores = [_safe_int(a.get("score"), 0) for a in analyses]
    fluency_scores = [_safe_int(a.get("fluency_score"), 0) for a in analyses]
    stuck_total = sum(
        len(a.get("stuck_events") or [])
        + _safe_int(a.get("repetitions"), 0)
        + _safe_int(a.get("restarts"), 0)
        + _safe_int(a.get("long_blocks"), 0)
        for a in analyses
    )
    wpm_values = [_safe_float(a.get("wpm"), 0.0) for a in analyses]

    overall = round(sum(overall_scores) / len(overall_scores))
    fluency = round(sum(fluency_scores) / len(fluency_scores))
    wpm = Decimal(str(round(sum(wpm_values) / len(wpm_values), 2)))

    return overall, fluency, stuck_total, wpm


async def persist_fluency_session(
    db: AsyncSession,
    user: User,
    started_at: datetime,
    ended_at: datetime,
    status: SessionStatusEnum,
    analyses: list[dict],
) -> tuple[Session, FluencyMetrics] | None:
    """Insert one sessions row + 1:1 fluency_metrics row at WS close.

    Returns None when there were no analyses to aggregate: an empty WS
    session (user opened the socket and disconnected without speaking) is
    not worth a row in history. The caller should treat None as "nothing
    to persist", not as an error.
    """

    if not analyses:
        return None

    overall, fluency, stuck, wpm = _aggregate_analyses(analyses)
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.fluency,
        parent_id=None,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        score=overall,
        status=status,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = FluencyMetrics(
        session_id=session_row.id,
        fluency_score=fluency,
        stuck_events_count=stuck,
        words_per_minute=wpm,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def list_fluency_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, FluencyMetrics]]:
    """Timeline of completed/aborted standalone fluency sessions for a user.

    parent_id IS NULL excludes sessions that belong to a live composition.
    Active sessions never appear here because fluency only persists at WS
    close; if a row is in the table it has already terminated.
    """

    query = (
        select(Session, FluencyMetrics)
        .join(FluencyMetrics, FluencyMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.fluency,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_fluency_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, FluencyMetrics] | None:
    """Detail of one fluency session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.fluency,
            )
        )
    ).scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_row = (
        await db.execute(
            select(FluencyMetrics).where(FluencyMetrics.session_id == session_id)
        )
    ).scalar_one_or_none()
    if metrics_row is None:
        return None

    return session_row, metrics_row
