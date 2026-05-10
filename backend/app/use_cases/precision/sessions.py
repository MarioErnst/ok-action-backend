from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import (
    ModuleEnum,
    PrecisionModeEnum,
    SessionStatusEnum,
)
from app.domain.entities.precision_metrics import PrecisionMetrics
from app.domain.entities.precision_round import PrecisionRound
from app.domain.entities.prompt import Prompt
from app.domain.entities.session import Session
from app.domain.entities.user import User


class SessionNotFoundError(Exception):
    """Session does not exist or does not belong to the calling user."""


class SessionNotActiveError(Exception):
    """Operation requires the session to be in 'active' status."""


class PromptNotAvailableError(Exception):
    """Prompt does not exist, is inactive, or does not belong to this module."""


class NotEnoughPromptsError(Exception):
    """Catalog has fewer active precision prompts than rounds_total."""


class RoundIndexOutOfRangeError(Exception):
    """round_index is outside [0, rounds_total) for the session."""


class RoundAlreadyEvaluatedError(Exception):
    """Same round_index has already been persisted for this session."""


def _round_score(relevance: int, directness: int, conciseness: int) -> int:
    """Weighted overall score for a single round.

    Weights match the prior implementation (relevance dominates) so the score
    a user sees today does not jump after the migration. If we ever decide to
    rebalance, change it here in one place.
    """

    return round(relevance * 0.4 + directness * 0.3 + conciseness * 0.3)


async def start_precision_session(
    db: AsyncSession,
    user: User,
    rounds_total: int,
) -> tuple[Session, PrecisionMetrics, list[Prompt]]:
    """Create an active precision session and pick its prompts.

    Inserts sessions(status='active', module='precision', parent_id=NULL,
    started_at=now) plus the 1:1 precision_metrics row. Picks rounds_total
    random active prompts from the catalog filtered by module='precision';
    raises NotEnoughPromptsError when the catalog has fewer than that.

    Returned prompts are NOT persisted as a per-session assignment; the
    client tracks which prompt belongs to which round_index and includes
    prompt_id in each evaluate_round call.
    """

    available = await db.execute(
        select(Prompt)
        .where(Prompt.module == ModuleEnum.precision, Prompt.is_active.is_(True))
        .order_by(func.random())
        .limit(rounds_total)
    )
    prompts = list(available.scalars().all())
    if len(prompts) < rounds_total:
        raise NotEnoughPromptsError(
            f"only {len(prompts)} active precision prompts available, "
            f"requested {rounds_total}"
        )

    started_at = datetime.now(timezone.utc)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.precision,
        parent_id=None,
        started_at=started_at,
        ended_at=None,
        duration_ms=None,
        score=None,
        status=SessionStatusEnum.active,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = PrecisionMetrics(
        session_id=session_row.id,
        mode=PrecisionModeEnum.standalone,
        rounds_total=rounds_total,
        rounds_completed=0,
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row, prompts


async def _load_active_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, PrecisionMetrics]:
    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.precision,
            )
        )
    ).scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        raise SessionNotFoundError(f"session {session_id} not found")
    if session_row.status != SessionStatusEnum.active:
        raise SessionNotActiveError(
            f"session {session_id} is {session_row.status.value}"
        )

    metrics_row = (
        await db.execute(
            select(PrecisionMetrics).where(PrecisionMetrics.session_id == session_id)
        )
    ).scalar_one()

    return session_row, metrics_row


async def evaluate_round(
    db: AsyncSession,
    user: User,
    session_id: UUID,
    round_index: int,
    prompt_id: UUID,
    gemini_evaluation: dict,
) -> PrecisionRound:
    """Persist a single round's evaluation.

    The router orchestrates the Gemini call (so the use_case stays free of
    HTTP and mime type concerns); this function just consumes the parsed
    evaluation dict. Validates that the session is active and the prompt
    exists and belongs to module='precision'. Increments rounds_completed.
    """

    session_row, metrics_row = await _load_active_session(db, user, session_id)

    if not (0 <= round_index < metrics_row.rounds_total):
        raise RoundIndexOutOfRangeError(
            f"round_index {round_index} outside [0, {metrics_row.rounds_total})"
        )

    prompt_row = (
        await db.execute(
            select(Prompt).where(
                Prompt.id == prompt_id,
                Prompt.module == ModuleEnum.precision,
                Prompt.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if prompt_row is None:
        raise PromptNotAvailableError(
            f"prompt {prompt_id} not found or not available for precision"
        )

    is_audio_intelligible = bool(gemini_evaluation["audio_intelligible"])
    if is_audio_intelligible:
        relevance = int(gemini_evaluation["relevance_score"])
        directness = int(gemini_evaluation["directness_score"])
        conciseness = int(gemini_evaluation["conciseness_score"])
        score = _round_score(relevance, directness, conciseness)
    else:
        relevance = directness = conciseness = score = None

    round_row = PrecisionRound(
        session_id=session_row.id,
        round_index=round_index,
        prompt_id=prompt_id,
        score=score,
        relevance_score=relevance,
        directness_score=directness,
        conciseness_score=conciseness,
        is_audio_intelligible=is_audio_intelligible,
    )
    db.add(round_row)

    metrics_row.rounds_completed = metrics_row.rounds_completed + 1

    try:
        await db.commit()
    except IntegrityError as exc:
        # Composite PK (session_id, round_index) already exists, typically
        # the frontend retried after the first request succeeded.
        await db.rollback()
        raise RoundAlreadyEvaluatedError(
            f"round_index {round_index} already evaluated for session {session_id}"
        ) from exc
    await db.refresh(round_row)
    await db.refresh(metrics_row)
    return round_row


async def finalize_precision_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, PrecisionMetrics]:
    """Aggregate intelligible rounds into the session score and metrics.

    Sets sessions.status='completed', ended_at=now, duration_ms, score = avg
    of intelligible round scores; also fills the per-dimension averages on
    precision_metrics. If no rounds were intelligible, score and the three
    aggregate sub-scores stay NULL — they are nullable in the schema.
    """

    session_row, metrics_row = await _load_active_session(db, user, session_id)

    rounds = (
        await db.execute(
            select(PrecisionRound).where(
                PrecisionRound.session_id == session_id,
                PrecisionRound.is_audio_intelligible.is_(True),
            )
        )
    ).scalars().all()

    if rounds:
        metrics_row.relevance_score = round(
            sum(r.relevance_score for r in rounds) / len(rounds)
        )
        metrics_row.directness_score = round(
            sum(r.directness_score for r in rounds) / len(rounds)
        )
        metrics_row.conciseness_score = round(
            sum(r.conciseness_score for r in rounds) / len(rounds)
        )
        session_row.score = round(sum(r.score for r in rounds) / len(rounds))
    else:
        metrics_row.relevance_score = None
        metrics_row.directness_score = None
        metrics_row.conciseness_score = None
        session_row.score = None

    ended_at = datetime.now(timezone.utc)
    session_row.ended_at = ended_at
    session_row.duration_ms = int(
        (ended_at - session_row.started_at).total_seconds() * 1000
    )
    session_row.status = SessionStatusEnum.completed

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)
    return session_row, metrics_row


async def abandon_precision_session(
    db: AsyncSession, user: User, session_id: UUID
) -> None:
    """Mark a session as aborted. Idempotent on already-aborted sessions
    (treated as a no-op so the user can hit the abandon button twice
    without seeing an error)."""

    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.precision,
            )
        )
    ).scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        raise SessionNotFoundError(f"session {session_id} not found")
    if session_row.status == SessionStatusEnum.aborted:
        return
    if session_row.status != SessionStatusEnum.active:
        raise SessionNotActiveError(
            f"session {session_id} is {session_row.status.value}"
        )

    ended_at = datetime.now(timezone.utc)
    session_row.ended_at = ended_at
    session_row.duration_ms = int(
        (ended_at - session_row.started_at).total_seconds() * 1000
    )
    session_row.status = SessionStatusEnum.aborted

    await db.commit()


async def list_precision_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, PrecisionMetrics]]:
    """Timeline of standalone precision sessions for a user, any status.

    parent_id IS NULL excludes sessions that belong to a live composition.
    Active and aborted sessions are included alongside completed ones so the
    UI can show "in progress" and "abandoned" entries when relevant.
    """

    query = (
        select(Session, PrecisionMetrics)
        .join(PrecisionMetrics, PrecisionMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.precision,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_precision_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, PrecisionMetrics, list[PrecisionRound]] | None:
    """Detail of one precision session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.precision,
            )
        )
    ).scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_row = (
        await db.execute(
            select(PrecisionMetrics).where(PrecisionMetrics.session_id == session_id)
        )
    ).scalar_one_or_none()
    if metrics_row is None:
        return None

    round_rows = list(
        (
            await db.execute(
                select(PrecisionRound)
                .where(PrecisionRound.session_id == session_id)
                .order_by(PrecisionRound.round_index)
            )
        )
        .scalars()
        .all()
    )

    return session_row, metrics_row, round_rows
