import logging
import random

from app.infrastructure.ai.muletillas_gemini import GeminiMuletillasService
from app.infrastructure.audio.silence_detector import is_silent

logger = logging.getLogger(__name__)

# Preguntas predefinidas para evaluacion de muletillas.
# En esta version no se generan con IA para simplificar la implementacion.
EVALUATION_QUESTIONS = [
    "Cuentame sobre tu dia de hoy.",
    "Describe tu lugar de trabajo o estudio.",
    "Explica en que consiste tu pasatiempo favorito.",
    "Habla sobre una pelicula o libro que hayas disfrutado recientemente.",
    "Describe un momento importante en tu vida.",
    "Que te motiva a mejorar tu comunicacion oral?",
    "Habla sobre alguien que admiras y por que.",
    "Describe el lugar donde creciste.",
]

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


def get_random_question() -> str:
    """Retorna una pregunta aleatoria de la lista predefinida."""
    return random.choice(EVALUATION_QUESTIONS)


async def evaluate_response(
    audio_bytes: bytes,
    mime_type: str,
    question_text: str,
) -> dict:
    """
    Detecta silencio y, si hay habla, evalua la respuesta con Gemini.
    Retorna el dict de evaluacion con scores y muletillas detectadas.
    """
    try:
        if await is_silent(audio_bytes, mime_type):
            return _SILENCE_RESPONSE
    except Exception as exc:
        logger.warning("Silence detection failed, proceeding to Gemini: %s", exc)

    service = GeminiMuletillasService()
    return await service.evaluate_response(audio_bytes, mime_type, question_text)
