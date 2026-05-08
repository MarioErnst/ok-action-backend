import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.linguistic_versatility_round import LinguisticVersatilityRound
from app.domain.entities.linguistic_versatility_session import LinguisticVersatilitySession
from app.infrastructure.ai.linguistic_versatility_gemini import (
    GeminiVersatilityService,
)

_gemini_service = GeminiVersatilityService()

# Allow-list mirrors what the frontend can produce (MediaRecorder MIME types).
# Anything outside falls back to webm so Gemini still attempts to decode it.
ALLOWED_MIME_TYPES = {"audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/mpeg"}


async def evaluate_versatility_response(
    db: AsyncSession,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    question_text: str,
    audio_bytes: bytes,
    mime_type: str,
) -> LinguisticVersatilityRound:
    """Evaluate one round and persist the result.

    Increments `completed_rounds` on the parent session only when Gemini
    returned an intelligible analysis — bad-audio rounds still get persisted
    (so the user sees them in history) but don't count against the total.
    """
    safe_mime = mime_type if mime_type in ALLOWED_MIME_TYPES else "audio/webm"

    result = await _gemini_service.evaluate_response(
        audio_bytes, safe_mime, question_text
    )

    round_entity = LinguisticVersatilityRound(
        session_id=session_id,
        question_id=question_id,
        question_text=question_text,
        audio_intelligible=bool(result["audio_intelligible"]),
    )

    if result["audio_intelligible"]:
        round_entity.versatility_score = result["versatility_score"]
        round_entity.vocabulary_richness = result["vocabulary_richness"]
        round_entity.feedback = result["feedback"]

        session = await db.get(LinguisticVersatilitySession, session_id)
        if session:
            session.completed_rounds += 1

    db.add(round_entity)
    await db.flush()
    return round_entity
