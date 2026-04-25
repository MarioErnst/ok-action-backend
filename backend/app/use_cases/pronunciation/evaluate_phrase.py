from app.infrastructure.ai.pronunciation_gemini import GeminiPronunciationService


async def evaluate_phrase(
    audio_bytes: bytes,
    mime_type: str,
    phrase_text: str,
    level: str,
) -> dict:
    service = GeminiPronunciationService()
    return await service.evaluate_phrase(audio_bytes, mime_type, phrase_text, level)
