import logging

from app.infrastructure.ai.pronunciation_gemini import GeminiPronunciationService
from app.infrastructure.audio.silence_detector import is_silent

logger = logging.getLogger(__name__)

_SILENCE_RESPONSE = {
    "overall_score": 0,
    "vowel_score": 0,
    "consonant_score": 0,
    "fluency_score": 0,
    "intelligibility_score": 0,
    "feedback": "No se detectó habla en el audio. Por favor graba tu voz leyendo la frase en voz alta.",
    "phoneme_errors": [],
}


async def evaluate_phrase(
    audio_bytes: bytes,
    mime_type: str,
    phrase_text: str,
    level: str,
) -> dict:
    try:
        if await is_silent(audio_bytes, mime_type):
            return _SILENCE_RESPONSE
    except Exception as exc:
        logger.warning("Silence detection failed, proceeding to Gemini: %s", exc)

    service = GeminiPronunciationService()
    return await service.evaluate_phrase(audio_bytes, mime_type, phrase_text, level)
