"""Persist the parsed Gemini composed evaluation as child sessions.

Given a Gemini response that conforms to the composed schema, this module
materializes one sessions row + one <modulo>_metrics row per selected
module, all hanging from the parent live session via parent_id. Score per
child is derived server-side using the same formula each standalone
module already uses, so a child created here is indistinguishable from
one created via the standalone endpoint.

When audio_intelligible is False we skip persistence entirely and return
an empty list. Live finalize will then aggregate over an empty children
set and produce score=NULL, which is the correct semantic for "the live
happened but produced no evaluable audio".
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.accentuation_metrics import AccentuationMetrics
from app.domain.entities.consistency_metrics import ConsistencyMetrics
from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.muletillas_metrics import MuletillasMetrics
from app.domain.entities.pronunciation_metrics import PronunciationMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.use_cases.live.composed.prompts import ComposableModule


def _clamp_pct(value: object, default: int = 0) -> int:
    """Coerce + clamp a Gemini int field into the 0-100 range that
    SmallInteger CHECK constraints accept. Single bad field never poisons
    the whole live evaluation."""

    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(100, n))


def _safe_int(value: object, default: int = 0) -> int:
    """Coerce a value into an int with a default fallback. Used for counts
    that are not bounded to 0-100."""

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _muletillas_score(section: dict) -> int:
    """Mirror standalone muletillas: session score equals fluency_score."""

    return _clamp_pct(section.get("fluency_score"))


def _accentuation_score(section: dict) -> int:
    """Mirror standalone accentuation: session score is the rounded average
    of the four sub-scores."""

    sub = [
        _clamp_pct(section.get("pronunciation_score")),
        _clamp_pct(section.get("rhythm_score")),
        _clamp_pct(section.get("intonation_score")),
        _clamp_pct(section.get("stress_score")),
    ]
    return round(sum(sub) / len(sub))


def _pronunciation_score(section: dict) -> int:
    """Mirror standalone pronunciation: session score is the rounded
    average of the four sub-scores."""

    sub = [
        _clamp_pct(section.get("vowel_score")),
        _clamp_pct(section.get("consonant_score")),
        _clamp_pct(section.get("fluency_score")),
        _clamp_pct(section.get("intelligibility_score")),
    ]
    return round(sum(sub) / len(sub))


def _consistency_score(section: dict) -> int:
    """Mirror standalone consistency: session score equals
    consistency_score."""

    return _clamp_pct(section.get("consistency_score"))


def _derive_volatility_score(volatility_count: int) -> int:
    """Standalone consistency derives volatility_score from the count of
    events: each event subtracts 20 points; 5+ bottoms out at 0. We keep
    the same formula here so live consistency rows look identical to
    standalone ones."""

    return max(0, 100 - volatility_count * 20)


async def persist_composed_evaluation(
    db: AsyncSession,
    user: User,
    parent_live_id: UUID,
    started_at: datetime,
    ended_at: datetime,
    modules: list[ComposableModule],
    gemini_response: dict,
) -> list[tuple[Session, object]]:
    """Insert one child session + metrics row per selected module.

    Each child shares the same started_at/ended_at because they all
    describe the same audio. duration_ms is derived server-side and is
    identical across siblings, which is consistent with the live being a
    single recording evaluated from multiple angles.

    Returns the list of (session, metrics) tuples that were created. If
    the audio was unintelligible, returns an empty list and persists
    nothing.
    """

    if not gemini_response.get("audio_intelligible"):
        return []

    duration_ms = int((ended_at - started_at).total_seconds() * 1000)
    created: list[tuple[Session, object]] = []

    for module in modules:
        section = gemini_response.get(module)
        if not isinstance(section, dict):
            continue

        if module == "muletillas":
            score = _muletillas_score(section)
            session_row = Session(
                user_id=user.id,
                module=ModuleEnum.muletillas,
                parent_id=parent_live_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                score=score,
                status=SessionStatusEnum.completed,
            )
            db.add(session_row)
            await db.flush()
            metrics_row = MuletillasMetrics(
                session_id=session_row.id,
                fluency_score=_clamp_pct(section.get("fluency_score")),
                muletillas_count=_safe_int(section.get("total_muletillas")),
            )
            db.add(metrics_row)
            created.append((session_row, metrics_row))

        elif module == "accentuation":
            score = _accentuation_score(section)
            session_row = Session(
                user_id=user.id,
                module=ModuleEnum.accentuation,
                parent_id=parent_live_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                score=score,
                status=SessionStatusEnum.completed,
            )
            db.add(session_row)
            await db.flush()
            metrics_row = AccentuationMetrics(
                session_id=session_row.id,
                pronunciation_score=_clamp_pct(section.get("pronunciation_score")),
                rhythm_score=_clamp_pct(section.get("rhythm_score")),
                intonation_score=_clamp_pct(section.get("intonation_score")),
                stress_score=_clamp_pct(section.get("stress_score")),
                phrases_count=0,
            )
            db.add(metrics_row)
            created.append((session_row, metrics_row))

        elif module == "pronunciation":
            score = _pronunciation_score(section)
            session_row = Session(
                user_id=user.id,
                module=ModuleEnum.pronunciation,
                parent_id=parent_live_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                score=score,
                status=SessionStatusEnum.completed,
            )
            db.add(session_row)
            await db.flush()
            metrics_row = PronunciationMetrics(
                session_id=session_row.id,
                level="free",
                vowel_score=_clamp_pct(section.get("vowel_score")),
                consonant_score=_clamp_pct(section.get("consonant_score")),
                fluency_score=_clamp_pct(section.get("fluency_score")),
                intelligibility_score=_clamp_pct(section.get("intelligibility_score")),
                phrases_count=0,
            )
            db.add(metrics_row)
            created.append((session_row, metrics_row))

        elif module == "consistency":
            score = _consistency_score(section)
            volatility_count = _safe_int(section.get("volatility_count"))
            session_row = Session(
                user_id=user.id,
                module=ModuleEnum.consistency,
                parent_id=parent_live_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                score=score,
                status=SessionStatusEnum.completed,
            )
            db.add(session_row)
            await db.flush()
            metrics_row = ConsistencyMetrics(
                session_id=session_row.id,
                consistency_score=_clamp_pct(section.get("consistency_score")),
                volatility_score=_derive_volatility_score(volatility_count),
                active_pct=_clamp_pct(section.get("active_pct")),
            )
            db.add(metrics_row)
            created.append((session_row, metrics_row))

    await db.commit()
    for session_row, metrics_row in created:
        await db.refresh(session_row)
        await db.refresh(metrics_row)

    return created
