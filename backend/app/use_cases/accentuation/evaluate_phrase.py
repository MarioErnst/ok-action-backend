# Logica de negocio del modulo de acentuacion: documentacion/modulos/acentuacion.md
import logging

from app.infrastructure.ai.gemini import GeminiAccentuationService
from app.infrastructure.audio.silence_detector import is_silent

logger = logging.getLogger(__name__)

_SILENCE_RESPONSE = {
    "overall_score": 0,
    "pronunciation_score": 0,
    "rhythm_score": 0,
    "intonation_score": 0,
    "stress_accuracy_score": 0,
    "feedback": "No se detectó habla en el audio. Por favor graba tu voz leyendo la frase en voz alta.",
    "specific_errors": [],
}


async def evaluate_phrase(
    audio_bytes: bytes,
    mime_type: str,
    phrase_text: str,
) -> dict:
    try:
        if await is_silent(audio_bytes, mime_type):
            return _SILENCE_RESPONSE
    except Exception as exc:
        logger.warning("Silence detection failed, proceeding to Gemini: %s", exc)

    service = GeminiAccentuationService()
    return await service.evaluate_phrase(audio_bytes, mime_type, phrase_text)
