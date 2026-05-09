from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.loudness_metrics import LoudnessMetrics
from app.domain.entities.loudness_preset import LoudnessPreset
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.presentation.schemas.loudness import LoudnessSessionCreate


class PresetNotAvailableError(Exception):
    """Raised when a session references a preset that the user cannot use."""


async def _resolve_preset(
    db: AsyncSession, user: User, preset_id: UUID
) -> LoudnessPreset:
    """Load a preset that is either global or owned by the user.

    Raises PresetNotAvailableError if the preset does not exist or belongs
    to another user. The router maps that to HTTP 422 because it is a
    payload validity error, not authorization on a sibling resource.
    """

    result = await db.execute(
        select(LoudnessPreset).where(
            LoudnessPreset.id == preset_id,
            or_(
                LoudnessPreset.user_id.is_(None),
                LoudnessPreset.user_id == user.id,
            ),
        )
    )
    preset = result.scalar_one_or_none()
    if preset is None:
        raise PresetNotAvailableError(
            f"preset {preset_id} not found or not available for this user"
        )
    return preset


async def create_loudness_session(
    db: AsyncSession,
    user: User,
    payload: LoudnessSessionCreate,
) -> tuple[Session, LoudnessMetrics]:
    """Persist a completed loudness session as one transaction.

    Inserts the root sessions row and the 1:1 loudness_metrics row. Server
    derives duration_ms from the time range and score from optimal_pct,
    matching the canonical loudness scoring rule (% time inside the optimal
    band). If a different scoring formula is needed in the future, change
    it here in one place.
    """

    await _resolve_preset(db, user, payload.metrics.preset_id)

    duration_ms = int((payload.ended_at - payload.started_at).total_seconds() * 1000)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.loudness,
        parent_id=None,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_ms=duration_ms,
        score=payload.metrics.optimal_pct,
        status=SessionStatusEnum.completed,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = LoudnessMetrics(
        session_id=session_row.id,
        preset_id=payload.metrics.preset_id,
        optimal_pct=payload.metrics.optimal_pct,
        low_pct=payload.metrics.low_pct,
        high_pct=payload.metrics.high_pct,
        clipping_pct=payload.metrics.clipping_pct,
        peak_db=payload.metrics.peak_db,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def list_loudness_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, LoudnessMetrics]]:
    """Timeline of completed standalone loudness sessions for a user.

    parent_id IS NULL filters out sessions that belong to a live composition;
    those should be exposed through the live module's history.
    """

    query = (
        select(Session, LoudnessMetrics)
        .join(LoudnessMetrics, LoudnessMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.loudness,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_loudness_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, LoudnessMetrics] | None:
    """Detail of one loudness session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.module == ModuleEnum.loudness,
        )
    )
    session_row = session_result.scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_result = await db.execute(
        select(LoudnessMetrics).where(LoudnessMetrics.session_id == session_id)
    )
    metrics_row = metrics_result.scalar_one_or_none()
    if metrics_row is None:
        return None

    return session_row, metrics_row
