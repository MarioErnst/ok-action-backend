from __future__ import annotations

import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import (
    ModuleEnum,
    MuletillaSeverityEnum,
    SessionStatusEnum,
)
from app.domain.entities.muletillas_metrics import MuletillasMetrics
from app.domain.entities.muletillas_word_usage import MuletillasWordUsage
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.presentation.schemas.muletillas import MuletillasSessionCreate


class DuplicateMuletillaWordError(Exception):
    """Raised when two payload entries normalize to the same word."""


def _normalize_word(word: str) -> str:
    """Lowercase, trim and strip combining accent marks per the proposal.

    Punctuation is left intact: typical muletillas do not carry trailing
    punctuation in Gemini's output, and stripping it would broaden the
    surface forms the function maps together in non-obvious ways.
    """

    decomposed = unicodedata.normalize("NFKD", word.strip().lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


async def create_muletillas_session(
    db: AsyncSession,
    user: User,
    payload: MuletillasSessionCreate,
) -> tuple[Session, MuletillasMetrics, list[MuletillasWordUsage]]:
    """Persist a completed muletillas session as one transaction.

    Inserts the root sessions row, the 1:1 muletillas_metrics row, and one
    muletillas_word_usage row per normalized word. duration_ms is derived
    from the time range; score equals fluency_score because muletillas has
    a single canonical scoring rule (precedent: loudness). muletillas_count
    is derived as the sum of per-word counts so the client cannot send a
    redundant field that drifts from the words list.
    """

    # Normalize and dedup-check before any write so we either insert all rows
    # or none, without relying on the composite PK to surface IntegrityError
    # mid-transaction.
    normalized_words: list[tuple[str, int, MuletillaSeverityEnum]] = []
    seen: set[str] = set()
    for word_input in payload.metrics.words:
        normalized = _normalize_word(word_input.word)
        if not normalized:
            raise DuplicateMuletillaWordError(
                f"word '{word_input.word}' is empty after normalization"
            )
        if normalized in seen:
            raise DuplicateMuletillaWordError(
                f"word '{normalized}' appears more than once after normalization"
            )
        seen.add(normalized)
        normalized_words.append(
            (
                normalized,
                word_input.count,
                MuletillaSeverityEnum(word_input.severity),
            )
        )

    duration_ms = int((payload.ended_at - payload.started_at).total_seconds() * 1000)
    muletillas_count = sum(count for _, count, _ in normalized_words)
    score = payload.metrics.fluency_score

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.muletillas,
        parent_id=None,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_ms=duration_ms,
        score=score,
        status=SessionStatusEnum.completed,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = MuletillasMetrics(
        session_id=session_row.id,
        fluency_score=payload.metrics.fluency_score,
        muletillas_count=muletillas_count,
    )
    db.add(metrics_row)

    word_rows = [
        MuletillasWordUsage(
            session_id=session_row.id,
            word=normalized,
            count=count,
            severity=severity,
        )
        for normalized, count, severity in normalized_words
    ]
    db.add_all(word_rows)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)

    word_rows.sort(key=lambda row: row.word)
    return session_row, metrics_row, word_rows


async def list_muletillas_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, MuletillasMetrics]]:
    """Timeline of completed standalone muletillas sessions for a user.

    parent_id IS NULL excludes sessions that belong to a live composition;
    those should be exposed through the live module's history.
    """

    query = (
        select(Session, MuletillasMetrics)
        .join(MuletillasMetrics, MuletillasMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.muletillas,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_muletillas_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, MuletillasMetrics, list[MuletillasWordUsage]] | None:
    """Detail of one muletillas session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.module == ModuleEnum.muletillas,
        )
    )
    session_row = session_result.scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_result = await db.execute(
        select(MuletillasMetrics).where(MuletillasMetrics.session_id == session_id)
    )
    metrics_row = metrics_result.scalar_one_or_none()
    if metrics_row is None:
        return None

    words_result = await db.execute(
        select(MuletillasWordUsage)
        .where(MuletillasWordUsage.session_id == session_id)
        .order_by(MuletillasWordUsage.word)
    )
    word_rows = list(words_result.scalars().all())

    return session_row, metrics_row, word_rows
