"""Persist the parsed Gemini composed evaluation as child sessions.

Given a Gemini response that conforms to the composed schema, this module
materializes one sessions row + one <modulo>_metrics row per selected
module, all hanging from the parent live session via parent_id. Score per
child is derived server-side using the same formula each standalone
module already uses, so a child created here is indistinguishable from
one created via the standalone endpoint.

When audio_intelligible is False we skip persistence of audio-derived
modules and return an empty list. Live finalize will then aggregate over
an empty children set and produce score=NULL, which is the correct
semantic for "the live happened but produced no evaluable audio".

facial_expression is the one composable module whose data does not come
from Gemini's response. The browser computes emotion percentages from the
classifier stream and submits them as a separate facial_summary payload
to the finalize endpoint. We persist that payload directly into
facial_expression_metrics. Because it is not gated by audio
intelligibility, a facial_expression child can exist even when the audio
sections were skipped.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from decimal import Decimal

from app.domain.entities.enums import ModuleEnum, SessionStatusEnum, TopEmotionEnum
from app.domain.entities.facial_expression_metrics import FacialExpressionMetrics
from app.domain.entities.muletillas_metrics import MuletillasMetrics
from app.domain.entities.phonation_metrics import PhonationMetrics
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


def _normalize_facial_pcts(summary: dict) -> dict[str, int]:
    """Read the seven emotion percentages from the client payload and
    normalize so they sum to exactly 100 (BD CHECK constraint).

    Floor + redistribute the residual to the highest emotion so the sum
    lands on 100 deterministically. Any missing or invalid emotion field
    is treated as zero."""

    keys = ("happy_pct", "sad_pct", "angry_pct", "surprised_pct", "fearful_pct", "disgusted_pct", "neutral_pct")
    pcts = {k: max(0, min(100, int(summary.get(k, 0) or 0))) for k in keys}
    total = sum(pcts.values())
    if total == 0:
        pcts["neutral_pct"] = 100
        return pcts
    if total == 100:
        return pcts
    # Scale + truncate, redistribute residual.
    scaled = {k: int(v * 100 / total) for k, v in pcts.items()}
    residual = 100 - sum(scaled.values())
    if residual != 0:
        top_key = max(scaled, key=lambda k: scaled[k])
        scaled[top_key] += residual
    return scaled


def _top_emotion(pcts: dict[str, int]) -> TopEmotionEnum:
    """Pick the highest-percent emotion as top_emotion. Ties resolve to
    the order defined in TopEmotionEnum (whichever value member of the
    enum comes first wins)."""

    mapping = {
        "happy_pct": TopEmotionEnum.happy,
        "sad_pct": TopEmotionEnum.sad,
        "angry_pct": TopEmotionEnum.angry,
        "surprised_pct": TopEmotionEnum.surprised,
        "fearful_pct": TopEmotionEnum.fearful,
        "disgusted_pct": TopEmotionEnum.disgusted,
        "neutral_pct": TopEmotionEnum.neutral,
    }
    top_key = max(mapping.keys(), key=lambda k: pcts.get(k, 0))
    return mapping[top_key]


async def persist_composed_evaluation(
    db: AsyncSession,
    user: User,
    parent_live_id: UUID,
    started_at: datetime,
    ended_at: datetime,
    modules: list[ComposableModule],
    gemini_response: dict,
    facial_summary: dict | None = None,
    phonation_summary: dict | None = None,
    loudness_summary: dict | None = None,
) -> list[tuple[Session, object]]:
    """Insert one child session + metrics row per selected module.

    Each child shares the same started_at/ended_at because they all
    describe the same audio. duration_ms is derived server-side and is
    identical across siblings, which is consistent with the live being a
    single recording evaluated from multiple angles.

    Returns the list of (session, metrics) tuples that were created. When
    audio is unintelligible, the audio modules are skipped but
    facial_expression is still persisted if a facial_summary was provided
    (facial does not depend on audio).
    """

    duration_ms = int((ended_at - started_at).total_seconds() * 1000)
    created: list[tuple[Session, object]] = []
    audio_intelligible = bool(gemini_response.get("audio_intelligible"))

    for module in modules:
        if module == "muletillas":
            if not audio_intelligible:
                continue
            section = gemini_response.get("muletillas")
            if not isinstance(section, dict):
                continue
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

        elif module == "phonation":
            if not phonation_summary:
                continue
            # Client computes avg_hz, stability_score and breaks_count
            # from the AudioWorklet pitch frames. We trust the client
            # to send 0-100 for stability and non-negative integers for
            # counts; the entity CHECK constraint enforces the range.
            try:
                avg_hz = Decimal(str(phonation_summary.get("avg_hz", 0)))
            except (TypeError, ValueError):
                avg_hz = Decimal("0")
            stability_score = _clamp_pct(phonation_summary.get("stability_score"))
            breaks_count = _safe_int(phonation_summary.get("breaks_count"))
            # Live session is a single recording, not an exercise count.
            # We persist exercises_count=0 to make sessions created here
            # honest about their origin.
            session_row = Session(
                user_id=user.id,
                module=ModuleEnum.phonation,
                parent_id=parent_live_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                score=stability_score,
                status=SessionStatusEnum.completed,
            )
            db.add(session_row)
            await db.flush()
            metrics_row = PhonationMetrics(
                session_id=session_row.id,
                avg_hz=avg_hz,
                stability_score=stability_score,
                breaks_count=breaks_count,
                exercises_count=0,
            )
            db.add(metrics_row)
            created.append((session_row, metrics_row))

        elif module == "facial_expression":
            if not facial_summary:
                continue
            pcts = _normalize_facial_pcts(facial_summary)
            top = _top_emotion(pcts)
            # Expressiveness is the share of time NOT spent in neutral.
            expressiveness = max(0, min(100, 100 - pcts["neutral_pct"]))
            # Session score follows expressiveness as a starting point.
            score = expressiveness
            session_row = Session(
                user_id=user.id,
                module=ModuleEnum.facial_expression,
                parent_id=parent_live_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                score=score,
                status=SessionStatusEnum.completed,
            )
            db.add(session_row)
            await db.flush()
            metrics_row = FacialExpressionMetrics(
                session_id=session_row.id,
                expressiveness_score=expressiveness,
                top_emotion=top,
                happy_pct=pcts["happy_pct"],
                sad_pct=pcts["sad_pct"],
                angry_pct=pcts["angry_pct"],
                surprised_pct=pcts["surprised_pct"],
                fearful_pct=pcts["fearful_pct"],
                disgusted_pct=pcts["disgusted_pct"],
                neutral_pct=pcts["neutral_pct"],
            )
            db.add(metrics_row)
            created.append((session_row, metrics_row))

    await db.commit()
    for session_row, metrics_row in created:
        await db.refresh(session_row)
        await db.refresh(metrics_row)

    return created
