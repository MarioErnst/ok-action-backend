from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.accentuation_metrics import AccentuationMetrics
from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.presentation.schemas.accentuation import AccentuationSessionCreate
from app.use_cases.live.sessions import validate_parent_live_session


def _derive_overall_score(payload: AccentuationSessionCreate) -> int:
    """Round average of the four sub-scores. Single canonical formula so the
    server derives it instead of trusting a redundant client field. If a
    weighted formula is needed in the future, change it here in one place."""

    sub_scores = [
        payload.metrics.pronunciation_score,
        payload.metrics.rhythm_score,
        payload.metrics.intonation_score,
        payload.metrics.stress_score,
    ]
    return round(sum(sub_scores) / len(sub_scores))


async def create_accentuation_session(
    db: AsyncSession,
    user: User,
    payload: AccentuationSessionCreate,
) -> tuple[Session, AccentuationMetrics]:
    """Persist a completed accentuation session as one transaction.

    Inserts the root sessions row and the 1:1 accentuation_metrics row.
    duration_ms is derived from the time range; score is derived as the
    average of the four sub-scores (precedent: loudness derives score from
    a single canonical formula instead of trusting client-side aggregates).
    """

    if payload.parent_id is not None:
        await validate_parent_live_session(db, user, payload.parent_id)

    duration_ms = int((payload.ended_at - payload.started_at).total_seconds() * 1000)
    score = _derive_overall_score(payload)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.accentuation,
        parent_id=payload.parent_id,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_ms=duration_ms,
        score=score,
        status=SessionStatusEnum.completed,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = AccentuationMetrics(
        session_id=session_row.id,
        pronunciation_score=payload.metrics.pronunciation_score,
        rhythm_score=payload.metrics.rhythm_score,
        intonation_score=payload.metrics.intonation_score,
        stress_score=payload.metrics.stress_score,
        phrases_count=payload.metrics.phrases_count,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def list_accentuation_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, AccentuationMetrics]]:
    """Timeline of completed standalone accentuation sessions for a user.

    parent_id IS NULL excludes sessions that belong to a live composition;
    those should be exposed through the live module's history.
    """

    query = (
        select(Session, AccentuationMetrics)
        .join(AccentuationMetrics, AccentuationMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.accentuation,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_accentuation_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, AccentuationMetrics] | None:
    """Detail of one accentuation session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.module == ModuleEnum.accentuation,
        )
    )
    session_row = session_result.scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_result = await db.execute(
        select(AccentuationMetrics).where(AccentuationMetrics.session_id == session_id)
    )
    metrics_row = metrics_result.scalar_one_or_none()
    if metrics_row is None:
        return None

    return session_row, metrics_row
