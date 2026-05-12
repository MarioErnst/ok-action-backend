from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import (
    LinguisticVersatilityModeEnum,
    ModuleEnum,
    SessionStatusEnum,
)
from app.domain.entities.linguistic_versatility_metrics import (
    LinguisticVersatilityMetrics,
)
from app.domain.entities.linguistic_versatility_round import (
    LinguisticVersatilityRound,
)
from app.domain.entities.prompt import Prompt
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.use_cases.live.sessions import validate_parent_live_session


class SessionNotFoundError(Exception):
    """Session does not exist or does not belong to the calling user."""


class SessionNotActiveError(Exception):
    """Operation requires the session to be in 'active' status."""


class PromptNotAvailableError(Exception):
    """Prompt does not exist, is inactive, or does not belong to this module."""


class NotEnoughPromptsError(Exception):
    """Catalog has fewer active prompts than rounds_total for guided mode."""


class RoundIndexOutOfRangeError(Exception):
    """round_index is outside [0, rounds_total) for the session."""


class RoundAlreadyEvaluatedError(Exception):
    """Same round_index has already been persisted for this session."""


class PromptModeMismatchError(Exception):
    """prompt_id required in guided mode and forbidden in free mode."""


async def start_linguistic_versatility_session(
    db: AsyncSession,
    user: User,
    mode: LinguisticVersatilityModeEnum,
    rounds_total: int,
    parent_id: UUID | None = None,
) -> tuple[Session, LinguisticVersatilityMetrics, list[Prompt]]:
    """Create an active session and pick prompts when in guided mode.

    When parent_id is given, the session is attached to the live composition
    via Session.parent_id. Unlike precision, the metrics.mode here is
    independent of the live attachment (guided/free is the user-facing
    practice mode); a guided round under a live and a guided round
    standalone differ only in the parent_id linkage.

    For guided mode picks rounds_total random active prompts from the
    catalog filtered by module='linguistic_versatility'; raises
    NotEnoughPromptsError if the catalog is too small. For free mode the
    returned prompt list is empty: free rounds carry prompt_id=NULL.
    """

    if parent_id is not None:
        await validate_parent_live_session(db, user, parent_id)

    if mode == LinguisticVersatilityModeEnum.guided:
        available = await db.execute(
            select(Prompt)
            .where(
                Prompt.module == ModuleEnum.linguistic_versatility,
                Prompt.is_active.is_(True),
            )
            .order_by(func.random())
            .limit(rounds_total)
        )
        prompts = list(available.scalars().all())
        if len(prompts) < rounds_total:
            raise NotEnoughPromptsError(
                f"only {len(prompts)} active linguistic_versatility prompts "
                f"available, requested {rounds_total}"
            )
    else:
        prompts = []

    started_at = datetime.now(timezone.utc)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.linguistic_versatility,
        parent_id=parent_id,
        started_at=started_at,
        ended_at=None,
        duration_ms=None,
        score=None,
        status=SessionStatusEnum.active,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = LinguisticVersatilityMetrics(
        session_id=session_row.id,
        mode=mode,
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
) -> tuple[Session, LinguisticVersatilityMetrics]:
    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.linguistic_versatility,
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
            select(LinguisticVersatilityMetrics).where(
                LinguisticVersatilityMetrics.session_id == session_id
            )
        )
    ).scalar_one()

    return session_row, metrics_row


async def evaluate_round(
    db: AsyncSession,
    user: User,
    session_id: UUID,
    round_index: int,
    prompt_id: UUID | None,
    gemini_evaluation: dict,
) -> LinguisticVersatilityRound:
    """Persist a single round's evaluation.

    The router orchestrates the Gemini call; this function consumes the
    parsed evaluation dict. Validates session is active, round_index is in
    [0, rounds_total), and the prompt_id pairing matches the session mode
    (required in guided, forbidden in free). Catches the composite-PK
    IntegrityError on duplicate round_index so a frontend retry returns
    409 instead of a raw 500.
    """

    session_row, metrics_row = await _load_active_session(db, user, session_id)

    if not (0 <= round_index < metrics_row.rounds_total):
        raise RoundIndexOutOfRangeError(
            f"round_index {round_index} outside [0, {metrics_row.rounds_total})"
        )

    if metrics_row.mode == LinguisticVersatilityModeEnum.guided:
        if prompt_id is None:
            raise PromptModeMismatchError(
                "prompt_id is required in guided mode"
            )
        prompt_row = (
            await db.execute(
                select(Prompt).where(
                    Prompt.id == prompt_id,
                    Prompt.module == ModuleEnum.linguistic_versatility,
                    Prompt.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if prompt_row is None:
            raise PromptNotAvailableError(
                f"prompt {prompt_id} not found or not available for "
                f"linguistic_versatility"
            )
    else:
        if prompt_id is not None:
            raise PromptModeMismatchError(
                "prompt_id must be omitted in free mode"
            )

    is_audio_intelligible = bool(gemini_evaluation["audio_intelligible"])
    if is_audio_intelligible:
        score = int(gemini_evaluation["versatility_score"])
        richness = int(gemini_evaluation["vocabulary_richness"])
    else:
        score = None
        richness = None

    round_row = LinguisticVersatilityRound(
        session_id=session_row.id,
        round_index=round_index,
        prompt_id=prompt_id,
        score=score,
        vocabulary_richness=richness,
        is_audio_intelligible=is_audio_intelligible,
    )
    db.add(round_row)

    metrics_row.rounds_completed = metrics_row.rounds_completed + 1

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise RoundAlreadyEvaluatedError(
            f"round_index {round_index} already evaluated for session {session_id}"
        ) from exc
    await db.refresh(round_row)
    await db.refresh(metrics_row)
    return round_row


async def finalize_linguistic_versatility_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, LinguisticVersatilityMetrics]:
    """Aggregate intelligible rounds into the session score and metrics.

    Sets sessions.status='completed', ended_at=now, duration_ms, score = avg
    of intelligible round scores; vocabulary_richness_avg = avg of
    intelligible richnesses. If no rounds were intelligible, both stay NULL.
    """

    session_row, metrics_row = await _load_active_session(db, user, session_id)

    rounds = (
        await db.execute(
            select(LinguisticVersatilityRound).where(
                LinguisticVersatilityRound.session_id == session_id,
                LinguisticVersatilityRound.is_audio_intelligible.is_(True),
            )
        )
    ).scalars().all()

    if rounds:
        metrics_row.vocabulary_richness_avg = round(
            sum(r.vocabulary_richness for r in rounds) / len(rounds)
        )
        session_row.score = round(sum(r.score for r in rounds) / len(rounds))
    else:
        metrics_row.vocabulary_richness_avg = None
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


async def abandon_linguistic_versatility_session(
    db: AsyncSession, user: User, session_id: UUID
) -> None:
    """Mark a session as aborted. Idempotent on already-aborted sessions."""

    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.linguistic_versatility,
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


async def list_linguistic_versatility_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, LinguisticVersatilityMetrics]]:
    """Timeline of standalone sessions for a user, any status.

    parent_id IS NULL excludes sessions that belong to a live composition.
    """

    query = (
        select(Session, LinguisticVersatilityMetrics)
        .join(
            LinguisticVersatilityMetrics,
            LinguisticVersatilityMetrics.session_id == Session.id,
        )
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.linguistic_versatility,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_linguistic_versatility_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, LinguisticVersatilityMetrics, list[LinguisticVersatilityRound]] | None:
    """Detail of one session owned by the given user."""

    session_row = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.module == ModuleEnum.linguistic_versatility,
            )
        )
    ).scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_row = (
        await db.execute(
            select(LinguisticVersatilityMetrics).where(
                LinguisticVersatilityMetrics.session_id == session_id
            )
        )
    ).scalar_one_or_none()
    if metrics_row is None:
        return None

    round_rows = list(
        (
            await db.execute(
                select(LinguisticVersatilityRound)
                .where(LinguisticVersatilityRound.session_id == session_id)
                .order_by(LinguisticVersatilityRound.round_index)
            )
        )
        .scalars()
        .all()
    )

    return session_row, metrics_row, round_rows
