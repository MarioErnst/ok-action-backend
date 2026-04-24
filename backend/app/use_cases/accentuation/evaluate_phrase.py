from app.infrastructure.ai.gemini import GeminiAccentuationService


async def evaluate_phrase(
    audio_bytes: bytes,
    mime_type: str,
    phrase_text: str,
) -> dict:
    service = GeminiAccentuationService()
    return await service.evaluate_phrase(audio_bytes, mime_type, phrase_text)
