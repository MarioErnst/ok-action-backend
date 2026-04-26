from app.infrastructure.ai.gemini import GeminiAccentuationService
from app.infrastructure.ai.speech_validator import GeminiSpeechValidator
from app.infrastructure.audio.silence_detector import is_silent

_SILENCE_RESPONSE = {
    "overall_score": 0,
    "pronunciation_score": 0,
    "rhythm_score": 0,
    "intonation_score": 0,
    "stress_accuracy_score": 0,
    "feedback": "No se detectó habla en el audio. Por favor graba tu voz leyendo la frase en voz alta.",
    "specific_errors": [],
}

_MISMATCH_RESPONSE = {
    "overall_score": 10,
    "pronunciation_score": 10,
    "rhythm_score": 10,
    "intonation_score": 5,
    "stress_accuracy_score": 5,
    "feedback": "El audio no corresponde a la frase indicada. Asegúrate de leer exactamente la frase mostrada en pantalla.",
    "specific_errors": [],
}


async def evaluate_phrase(
    audio_bytes: bytes,
    mime_type: str,
    phrase_text: str,
) -> dict:
    if await is_silent(audio_bytes, mime_type):
        return _SILENCE_RESPONSE

    validator = GeminiSpeechValidator()
    validation = await validator.validate(audio_bytes, mime_type, phrase_text)

    if not validation.get("has_speech"):
        return _SILENCE_RESPONSE

    if not validation.get("matches_phrase"):
        return _MISMATCH_RESPONSE

    service = GeminiAccentuationService()
    return await service.evaluate_phrase(audio_bytes, mime_type, phrase_text)
