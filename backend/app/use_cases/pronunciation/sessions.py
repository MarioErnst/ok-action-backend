from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.pronunciation_metrics import PronunciationMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.presentation.schemas.pronunciation import PronunciationSessionCreate
from app.use_cases.live.sessions import validate_parent_live_session


def _derive_overall_score(payload: PronunciationSessionCreate) -> int:
    """Round average of the four sub-scores. Single canonical formula so the
    server derives it instead of trusting a redundant client field. If a
    weighted formula is needed in the future, change it here in one place."""

    sub_scores = [
        payload.metrics.vowel_score,
        payload.metrics.consonant_score,
        payload.metrics.fluency_score,
        payload.metrics.intelligibility_score,
    ]
    return round(sum(sub_scores) / len(sub_scores))


async def create_pronunciation_session(
    db: AsyncSession,
    user: User,
    payload: PronunciationSessionCreate,
) -> tuple[Session, PronunciationMetrics]:
    """Persist a completed pronunciation session as one transaction.

    Inserts the root sessions row and the 1:1 pronunciation_metrics row.
    duration_ms is derived from the time range; score is derived as the
    average of the four sub-scores (precedent: loudness/accentuation derive
    score from a single canonical formula).
    """

    if payload.parent_id is not None:
        await validate_parent_live_session(db, user, payload.parent_id)

    duration_ms = int((payload.ended_at - payload.started_at).total_seconds() * 1000)
    score = _derive_overall_score(payload)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.pronunciation,
        parent_id=payload.parent_id,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_ms=duration_ms,
        score=score,
        status=SessionStatusEnum.completed,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = PronunciationMetrics(
        session_id=session_row.id,
        level=payload.metrics.level,
        vowel_score=payload.metrics.vowel_score,
        consonant_score=payload.metrics.consonant_score,
        fluency_score=payload.metrics.fluency_score,
        intelligibility_score=payload.metrics.intelligibility_score,
        phrases_count=payload.metrics.phrases_count,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def list_pronunciation_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, PronunciationMetrics]]:
    """Timeline of completed standalone pronunciation sessions for a user.

    parent_id IS NULL excludes sessions that belong to a live composition;
    those should be exposed through the live module's history.
    """

    query = (
        select(Session, PronunciationMetrics)
        .join(PronunciationMetrics, PronunciationMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.pronunciation,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_pronunciation_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, PronunciationMetrics] | None:
    """Detail of one pronunciation session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.module == ModuleEnum.pronunciation,
        )
    )
    session_row = session_result.scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_result = await db.execute(
        select(PronunciationMetrics).where(
            PronunciationMetrics.session_id == session_id
        )
    )
    metrics_row = metrics_result.scalar_one_or_none()
    if metrics_row is None:
        return None

    return session_row, metrics_row
