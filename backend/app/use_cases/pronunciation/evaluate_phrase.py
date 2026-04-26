from app.infrastructure.ai.pronunciation_gemini import GeminiPronunciationService
from app.infrastructure.ai.speech_validator import GeminiSpeechValidator
from app.infrastructure.audio.silence_detector import is_silent

_SILENCE_RESPONSE = {
    "overall_score": 0,
    "vowel_score": 0,
    "consonant_score": 0,
    "fluency_score": 0,
    "intelligibility_score": 0,
    "feedback": "No se detectó habla en el audio. Por favor graba tu voz leyendo la frase en voz alta.",
    "phoneme_errors": [],
}

_MISMATCH_RESPONSE = {
    "overall_score": 10,
    "vowel_score": 10,
    "consonant_score": 10,
    "fluency_score": 5,
    "intelligibility_score": 5,
    "feedback": "El audio no corresponde a la frase indicada. Asegúrate de leer exactamente la frase mostrada en pantalla.",
    "phoneme_errors": [],
}


async def evaluate_phrase(
    audio_bytes: bytes,
    mime_type: str,
    phrase_text: str,
    level: str,
) -> dict:
    if await is_silent(audio_bytes, mime_type):
        return _SILENCE_RESPONSE

    validator = GeminiSpeechValidator()
    validation = await validator.validate(audio_bytes, mime_type, phrase_text)

    if not validation.get("has_speech"):
        return _SILENCE_RESPONSE

    if not validation.get("matches_phrase"):
        return _MISMATCH_RESPONSE

    service = GeminiPronunciationService()
    return await service.evaluate_phrase(audio_bytes, mime_type, phrase_text, level)
