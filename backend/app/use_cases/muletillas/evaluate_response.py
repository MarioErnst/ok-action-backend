# Business logic for the muletillas module: documentacion/modulos/muletillas.md
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum
from app.domain.entities.prompt import Prompt
from app.infrastructure.ai.muletillas_gemini import GeminiMuletillasService
from app.infrastructure.audio.silence_detector import is_silent

logger = logging.getLogger(__name__)


class NoMuletillasPromptsError(RuntimeError):
    """Raised when the prompts catalog has no active muletillas prompts.

    Distinct from a generic 500 so the router can surface a 503 telling the
    client that the catalog is empty (typically a seed-not-run state).
    """


_SILENCE_RESPONSE = {
    "overall_score": 0,
    "fluency_score": 0,
    "muletillas_score": 0,
    "total_muletillas_count": 0,
    "muletillas_per_minute": 0.0,
    "muletillas_detected": [],
    "feedback": "No se detecto habla en el audio. Por favor graba tu voz respondiendo la pregunta.",
    "strengths": "",
    "improvement_areas": "Asegurate de hablar claramente frente al microfono.",
}


async def get_random_question(db: AsyncSession) -> str:
    """Return one active muletillas prompt text picked randomly from the catalog.

    Uses Postgres `random()` to push selection to the database — the catalog
    is small today but the same pattern stays cheap as it grows. Raises
    NoMuletillasPromptsError if the catalog is empty so the router can map
    that to a 503 (seed pending) instead of an opaque 500.
    """

    result = await db.execute(
        select(Prompt.text)
        .where(Prompt.module == ModuleEnum.muletillas)
        .where(Prompt.is_active.is_(True))
        .order_by(func.random())
        .limit(1)
    )
    text = result.scalar_one_or_none()
    if text is None:
        raise NoMuletillasPromptsError(
            "No hay preguntas disponibles para muletillas"
        )
    return text


async def evaluate_response(
    audio_bytes: bytes,
    mime_type: str,
    question_text: str,
) -> dict:
    """
    Detects silence and, if speech is present, evaluates the response with Gemini.
    Returns the evaluation dict with scores and detected muletillas.
    """
    try:
        if await is_silent(audio_bytes, mime_type):
            return _SILENCE_RESPONSE
    except Exception as exc:
        logger.warning("Silence detection failed, proceeding to Gemini: %s", exc)

    service = GeminiMuletillasService()
    return await service.evaluate_response(audio_bytes, mime_type, question_text)
