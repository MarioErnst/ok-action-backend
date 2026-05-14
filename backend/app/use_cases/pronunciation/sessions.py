from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.prompt import Prompt
from app.domain.entities.pronunciation_metrics import PronunciationMetrics
from app.domain.entities.pronunciation_phrase_evaluation import (
    PronunciationPhraseEvaluation,
)
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.presentation.schemas.pronunciation import PronunciationSessionCreate
from app.use_cases.live.sessions import validate_parent_live_session


class PronunciationPromptNotAvailableError(ValueError):
    """Raised when a phrase prompt_id is unknown, inactive, or not from the
    pronunciation module. Router maps to 422.
    """


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


async def _validate_phrase_prompts(
    db: AsyncSession, payload: PronunciationSessionCreate
) -> None:
    """Confirm every prompt_id in the payload is an active pronunciation
    prompt. Single batched query for all ids.
    """

    if not payload.phrases:
        return
    ids = {p.prompt_id for p in payload.phrases}
    result = await db.execute(
        select(Prompt.id)
        .where(Prompt.id.in_(ids))
        .where(Prompt.module == ModuleEnum.pronunciation)
        .where(Prompt.is_active.is_(True))
    )
    found = {row[0] for row in result.all()}
    missing = ids - found
    if missing:
        raise PronunciationPromptNotAvailableError(
            f"prompts no disponibles para pronunciation: {sorted(str(i) for i in missing)}"
        )


async def create_pronunciation_session(
    db: AsyncSession,
    user: User,
    payload: PronunciationSessionCreate,
) -> tuple[Session, PronunciationMetrics]:
    """Persist a completed pronunciation session as one transaction.

    Inserts the root sessions row, the 1:1 pronunciation_metrics row, and N
    pronunciation_phrase_evaluations rows. duration_ms is derived from the
    time range; score is the average of the four sub-scores.
    """

    if payload.parent_id is not None:
        await validate_parent_live_session(db, user, payload.parent_id)

    await _validate_phrase_prompts(db, payload)

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

    for phrase in payload.phrases:
        db.add(
            PronunciationPhraseEvaluation(
                session_id=session_row.id,
                phrase_index=phrase.phrase_index,
                prompt_id=phrase.prompt_id,
                vowel_score=phrase.vowel_score,
                consonant_score=phrase.consonant_score,
                fluency_score=phrase.fluency_score,
                intelligibility_score=phrase.intelligibility_score,
            )
        )

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


async def list_session_phrases(
    db: AsyncSession, user: User, session_id: UUID
) -> list[dict] | None:
    """Return per-phrase rows of one session enriched with prompt text/difficulty.

    None if the session does not exist or belongs to another user (router →
    404). Empty list means the session was persisted before B7 rolled out.
    """

    owner_result = await db.execute(
        select(Session.user_id).where(
            Session.id == session_id,
            Session.module == ModuleEnum.pronunciation,
        )
    )
    owner = owner_result.scalar_one_or_none()
    if owner is None or owner != user.id:
        return None

    rows_result = await db.execute(
        select(
            PronunciationPhraseEvaluation.phrase_index,
            PronunciationPhraseEvaluation.prompt_id,
            Prompt.text.label("prompt_text"),
            Prompt.difficulty.label("prompt_difficulty"),
            PronunciationPhraseEvaluation.vowel_score,
            PronunciationPhraseEvaluation.consonant_score,
            PronunciationPhraseEvaluation.fluency_score,
            PronunciationPhraseEvaluation.intelligibility_score,
        )
        .join(Prompt, Prompt.id == PronunciationPhraseEvaluation.prompt_id)
        .where(PronunciationPhraseEvaluation.session_id == session_id)
        .order_by(PronunciationPhraseEvaluation.phrase_index)
    )
    return [dict(row._mapping) for row in rows_result.all()]


async def weakest_prompts(
    db: AsyncSession,
    user: User,
    limit: int = 5,
    min_practice_count: int = 1,
    difficulty: str | None = None,
) -> list[dict]:
    """Return the pronunciation prompts where the user has the lowest avg score.

    Per-row score is the average of the four sub-scores; aggregated across
    every evaluation by the user. `difficulty` (optional) narrows to one
    level so the UI can show "weakest at level X". `min_practice_count`
    filters out prompts with too little data.
    """

    if limit <= 0:
        return []

    avg_per_phrase = (
        (
            PronunciationPhraseEvaluation.vowel_score
            + PronunciationPhraseEvaluation.consonant_score
            + PronunciationPhraseEvaluation.fluency_score
            + PronunciationPhraseEvaluation.intelligibility_score
        )
        / 4.0
    )
    query = (
        select(
            PronunciationPhraseEvaluation.prompt_id,
            Prompt.text.label("text"),
            Prompt.difficulty.label("difficulty"),
            func.round(func.avg(avg_per_phrase)).label("avg_score"),
            func.count().label("practice_count"),
        )
        .join(Session, Session.id == PronunciationPhraseEvaluation.session_id)
        .join(Prompt, Prompt.id == PronunciationPhraseEvaluation.prompt_id)
        .where(Session.user_id == user.id)
        .group_by(
            PronunciationPhraseEvaluation.prompt_id,
            Prompt.text,
            Prompt.difficulty,
        )
        .having(func.count() >= min_practice_count)
        .order_by(func.avg(avg_per_phrase).asc())
        .limit(limit)
    )
    if difficulty is not None:
        query = query.where(Prompt.difficulty == difficulty)
    result = await db.execute(query)
    return [
        {
            "prompt_id": row.prompt_id,
            "text": row.text,
            "difficulty": row.difficulty,
            "avg_score": int(row.avg_score),
            "practice_count": int(row.practice_count),
        }
        for row in result.all()
    ]
