from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.body_expression_metrics import BodyExpressionMetrics
from app.domain.entities.enums import BodyFramingModeEnum, ModuleEnum, SessionStatusEnum
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.ai.body_expression_gemini import generate_body_expression_feedback
from app.presentation.schemas.body_expression import (
    BodyExpressionFeedbackOutput,
    BodyExpressionMetricsInput,
    BodyExpressionSessionCreate,
)
from app.use_cases.live.sessions import validate_parent_live_session

_GEMINI_TIMEOUT_SECONDS = 8


def derive_body_expression_score(metrics: BodyExpressionMetricsInput) -> int:
    score = (
        metrics.posture_score * 0.20
        + metrics.openness_score * 0.20
        + metrics.gesture_score * 0.20
        + metrics.stability_score * 0.15
        + metrics.energy_score * 0.15
        + metrics.framing_score * 0.10
    )
    return round(max(0, min(100, score)))


def build_rule_based_feedback(
    metrics: BodyExpressionMetricsInput,
) -> BodyExpressionFeedbackOutput:
    score = derive_body_expression_score(metrics)

    sorted_scores = sorted(
        [
            ("postura", metrics.posture_score),
            ("apertura corporal", metrics.openness_score),
            ("gesticulacion", metrics.gesture_score),
            ("estabilidad", metrics.stability_score),
            ("energia", metrics.energy_score),
            ("encuadre", metrics.framing_score),
        ],
        key=lambda item: item[1],
    )
    weakest_name, weakest_score = sorted_scores[0]
    strongest = [name for name, value in sorted_scores[-3:] if value >= 70]

    if score >= 80:
        summary = "Tu lenguaje corporal se ve solido y acompana bien el mensaje."
    elif score >= 60:
        summary = "Tu lenguaje corporal es funcional, con espacio para hacerlo mas claro y estable."
    else:
        summary = "Tu presencia corporal todavia puede ganar control, apertura y claridad visual."

    strengths = strongest or ["mantuviste una base corporal reconocible durante la practica"]
    improvements = [
        _improvement_for(weakest_name, weakest_score),
        _tracking_improvement(metrics),
    ]
    recommendation = _recommendation_for(weakest_name)

    return BodyExpressionFeedbackOutput(
        summary=summary,
        strengths=strengths[:3],
        improvements=list(dict.fromkeys(improvements))[:3],
        recommendation=recommendation,
        source="rules",
    )


async def build_ephemeral_feedback(
    payload: BodyExpressionSessionCreate,
) -> BodyExpressionFeedbackOutput:
    metrics = payload.metrics
    fallback = build_rule_based_feedback(metrics)
    metrics_dict = {
        "overall_score": derive_body_expression_score(metrics),
        "posture_score": metrics.posture_score,
        "openness_score": metrics.openness_score,
        "gesture_score": metrics.gesture_score,
        "stability_score": metrics.stability_score,
        "energy_score": metrics.energy_score,
        "framing_score": metrics.framing_score,
        "tracked_pct": metrics.tracked_pct,
        "hands_visible_pct": metrics.hands_visible_pct,
        "excessive_movement_pct": metrics.excessive_movement_pct,
        "calibration_quality_pct": metrics.calibration_quality_pct,
        "framing_mode": metrics.framing_mode,
    }

    try:
        raw = await asyncio.wait_for(
            generate_body_expression_feedback(payload.prompt_text or "", metrics_dict),
            timeout=_GEMINI_TIMEOUT_SECONDS,
        )
    except Exception:
        return fallback

    if not raw:
        return fallback

    try:
        return BodyExpressionFeedbackOutput(
            summary=str(raw.get("summary") or fallback.summary),
            strengths=_clean_text_list(raw.get("strengths")) or fallback.strengths,
            improvements=_clean_text_list(raw.get("improvements")) or fallback.improvements,
            recommendation=str(raw.get("recommendation") or fallback.recommendation),
            source="gemini",
        )
    except Exception:
        return fallback


async def create_body_expression_session(
    db: AsyncSession,
    user: User,
    payload: BodyExpressionSessionCreate,
) -> tuple[Session, BodyExpressionMetrics, BodyExpressionFeedbackOutput]:
    if payload.parent_id is not None:
        await validate_parent_live_session(db, user, payload.parent_id)

    duration_ms = int((payload.ended_at - payload.started_at).total_seconds() * 1000)
    score = derive_body_expression_score(payload.metrics)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.body_expression,
        parent_id=payload.parent_id,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_ms=duration_ms,
        score=score,
        status=SessionStatusEnum.completed,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = BodyExpressionMetrics(
        session_id=session_row.id,
        posture_score=payload.metrics.posture_score,
        openness_score=payload.metrics.openness_score,
        gesture_score=payload.metrics.gesture_score,
        stability_score=payload.metrics.stability_score,
        energy_score=payload.metrics.energy_score,
        framing_score=payload.metrics.framing_score,
        tracked_pct=payload.metrics.tracked_pct,
        hands_visible_pct=payload.metrics.hands_visible_pct,
        excessive_movement_pct=payload.metrics.excessive_movement_pct,
        calibration_quality_pct=payload.metrics.calibration_quality_pct,
        framing_mode=BodyFramingModeEnum(payload.metrics.framing_mode),
    )
    db.add(metrics_row)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)

    feedback = await build_ephemeral_feedback(payload)
    return session_row, metrics_row, feedback


async def list_body_expression_sessions(
    db: AsyncSession, user: User
) -> list[tuple[Session, BodyExpressionMetrics]]:
    query = (
        select(Session, BodyExpressionMetrics)
        .join(BodyExpressionMetrics, BodyExpressionMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.body_expression,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_body_expression_session(
    db: AsyncSession, user: User, session_id: UUID
) -> tuple[Session, BodyExpressionMetrics] | None:
    result = await db.execute(
        select(Session, BodyExpressionMetrics)
        .join(BodyExpressionMetrics, BodyExpressionMetrics.session_id == Session.id)
        .where(
            Session.id == session_id,
            Session.user_id == user.id,
            Session.module == ModuleEnum.body_expression,
        )
    )
    return result.one_or_none()


def feedback_from_metrics_row(metrics_row: BodyExpressionMetrics) -> BodyExpressionFeedbackOutput:
    metrics = BodyExpressionMetricsInput(
        posture_score=metrics_row.posture_score,
        openness_score=metrics_row.openness_score,
        gesture_score=metrics_row.gesture_score,
        stability_score=metrics_row.stability_score,
        energy_score=metrics_row.energy_score,
        framing_score=metrics_row.framing_score,
        tracked_pct=metrics_row.tracked_pct,
        hands_visible_pct=metrics_row.hands_visible_pct,
        excessive_movement_pct=metrics_row.excessive_movement_pct,
        calibration_quality_pct=metrics_row.calibration_quality_pct,
        framing_mode=metrics_row.framing_mode.value,
    )
    return build_rule_based_feedback(metrics)


def _clean_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:3]


def _improvement_for(name: str, score: int) -> str:
    if score >= 70:
        return "mantener el mismo criterio y buscar mas naturalidad en la siguiente practica"
    mapping = {
        "postura": "alinear hombros y torso antes de responder para proyectar mas seguridad",
        "apertura corporal": "evitar cerrar brazos o manos frente al torso por demasiado tiempo",
        "gesticulacion": "usar gestos visibles para acompanar ideas clave sin mover las manos todo el tiempo",
        "estabilidad": "reducir balanceos o desplazamientos bruscos durante la respuesta",
        "energia": "sumar intencion corporal en los puntos importantes del mensaje",
        "encuadre": "ubicarte centrado y con hombros y manos visibles para una medicion mas confiable",
    }
    return mapping.get(name, f"mejorar {name}")


def _tracking_improvement(metrics: BodyExpressionMetricsInput) -> str:
    if metrics.tracked_pct < 65:
        return "mejorar iluminacion y distancia a la camara para sostener la deteccion"
    if metrics.hands_visible_pct < 45:
        return "mantener las manos dentro del encuadre cuando uses gestos"
    if metrics.excessive_movement_pct > 35:
        return "evitar movimientos rapidos que distraigan del mensaje"
    return "repetir la practica con una consigna mas desafiante para comparar progreso"


def _recommendation_for(name: str) -> str:
    mapping = {
        "postura": "Antes de hablar, respira, alinea hombros y conserva el torso estable durante los primeros 10 segundos.",
        "apertura corporal": "Practica responder con manos visibles y codos relajados, evitando cruzar brazos.",
        "gesticulacion": "Marca solo las ideas principales con gestos; vuelve a una postura neutra entre una idea y otra.",
        "estabilidad": "Ancla los pies y limita balanceos laterales mientras terminas cada frase.",
        "energia": "Sube la energia corporal en la introduccion y el cierre para que el mensaje tenga presencia.",
        "encuadre": "Ajusta la camara para que se vean hombros, torso y manos antes de iniciar.",
    }
    return mapping.get(name, "Repite la consigna enfocandote en un solo ajuste corporal a la vez.")
