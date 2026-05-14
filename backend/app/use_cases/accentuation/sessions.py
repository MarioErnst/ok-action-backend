from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.accentuation_metrics import AccentuationMetrics
from app.domain.entities.accentuation_phrase_evaluation import (
    AccentuationPhraseEvaluation,
)
from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.prompt import Prompt
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.presentation.schemas.accentuation import AccentuationSessionCreate
from app.use_cases.live.sessions import validate_parent_live_session


class AccentuationPromptNotAvailableError(ValueError):
    """Raised when a phrase prompt_id is unknown, inactive, or not from the
    accentuation module. Router maps to 422.
    """


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


async def _validate_phrase_prompts(
    db: AsyncSession, payload: AccentuationSessionCreate
) -> None:
    """Confirm every prompt_id in the payload is an active accentuation prompt.

    A single batched query for all ids; raises if any id is missing,
    inactive, or from a different module. Cheaper than N point lookups and
    keeps the create path atomic.
    """

    if not payload.phrases:
        return
    ids = {p.prompt_id for p in payload.phrases}
    result = await db.execute(
        select(Prompt.id)
        .where(Prompt.id.in_(ids))
        .where(Prompt.module == ModuleEnum.accentuation)
        .where(Prompt.is_active.is_(True))
    )
    found = {row[0] for row in result.all()}
    missing = ids - found
    if missing:
        raise AccentuationPromptNotAvailableError(
            f"prompts no disponibles para accentuation: {sorted(str(i) for i in missing)}"
        )


async def create_accentuation_session(
    db: AsyncSession,
    user: User,
    payload: AccentuationSessionCreate,
) -> tuple[Session, AccentuationMetrics]:
    """Persist a completed accentuation session as one transaction.

    Inserts the root sessions row, the 1:1 accentuation_metrics row, and N
    accentuation_phrase_evaluations rows (one per phrase). duration_ms is
    derived from the time range; score is the average of the four
    sub-scores. Every prompt_id in `payload.phrases` is validated against
    the catalog before the inserts.
    """

    if payload.parent_id is not None:
        await validate_parent_live_session(db, user, payload.parent_id)

    await _validate_phrase_prompts(db, payload)

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

    for phrase in payload.phrases:
        db.add(
            AccentuationPhraseEvaluation(
                session_id=session_row.id,
                phrase_index=phrase.phrase_index,
                prompt_id=phrase.prompt_id,
                pronunciation_score=phrase.pronunciation_score,
                rhythm_score=phrase.rhythm_score,
                intonation_score=phrase.intonation_score,
                stress_score=phrase.stress_score,
            )
        )

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


async def list_session_phrases(
    db: AsyncSession, user: User, session_id: UUID
) -> list[dict] | None:
    """Return per-phrase rows of one session enriched with prompt text/category.

    None if the session does not exist or belongs to another user (router →
    404). Empty list means the session was persisted before B7 rolled out.
    """

    owner_result = await db.execute(
        select(Session.user_id).where(
            Session.id == session_id,
            Session.module == ModuleEnum.accentuation,
        )
    )
    owner = owner_result.scalar_one_or_none()
    if owner is None or owner != user.id:
        return None

    rows_result = await db.execute(
        select(
            AccentuationPhraseEvaluation.phrase_index,
            AccentuationPhraseEvaluation.prompt_id,
            Prompt.text.label("prompt_text"),
            Prompt.category.label("prompt_category"),
            AccentuationPhraseEvaluation.pronunciation_score,
            AccentuationPhraseEvaluation.rhythm_score,
            AccentuationPhraseEvaluation.intonation_score,
            AccentuationPhraseEvaluation.stress_score,
        )
        .join(Prompt, Prompt.id == AccentuationPhraseEvaluation.prompt_id)
        .where(AccentuationPhraseEvaluation.session_id == session_id)
        .order_by(AccentuationPhraseEvaluation.phrase_index)
    )
    return [dict(row._mapping) for row in rows_result.all()]


async def weakest_prompts(
    db: AsyncSession, user: User, limit: int = 5, min_practice_count: int = 1
) -> list[dict]:
    """Return the prompts where the user has the lowest avg score so far.

    The score per row is the average of the four sub-scores rounded to int,
    aggregated across every evaluation by the user. `min_practice_count`
    filters out prompts with too little data (set to 2+ in the UI to avoid
    surfacing a single bad attempt). The query joins prompts to expose
    text/category to the UI without a second round-trip.
    """

    if limit <= 0:
        return []

    avg_per_phrase = (
        (
            AccentuationPhraseEvaluation.pronunciation_score
            + AccentuationPhraseEvaluation.rhythm_score
            + AccentuationPhraseEvaluation.intonation_score
            + AccentuationPhraseEvaluation.stress_score
        )
        / 4.0
    )
    query = (
        select(
            AccentuationPhraseEvaluation.prompt_id,
            Prompt.text.label("text"),
            Prompt.category.label("category"),
            func.round(func.avg(avg_per_phrase)).label("avg_score"),
            func.count().label("practice_count"),
        )
        .join(Session, Session.id == AccentuationPhraseEvaluation.session_id)
        .join(Prompt, Prompt.id == AccentuationPhraseEvaluation.prompt_id)
        .where(Session.user_id == user.id)
        .group_by(AccentuationPhraseEvaluation.prompt_id, Prompt.text, Prompt.category)
        .having(func.count() >= min_practice_count)
        .order_by(func.avg(avg_per_phrase).asc())
        .limit(limit)
    )
    result = await db.execute(query)
    return [
        {
            "prompt_id": row.prompt_id,
            "text": row.text,
            "category": row.category,
            "avg_score": int(row.avg_score),
            "practice_count": int(row.practice_count),
        }
        for row in result.all()
    ]
