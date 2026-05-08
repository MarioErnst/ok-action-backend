import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.linguistic_versatility_round import LinguisticVersatilityRound
from app.domain.entities.linguistic_versatility_session import LinguisticVersatilitySession
from app.infrastructure.ai.linguistic_versatility_gemini import (
    GeminiVersatilityService,
)
from app.use_cases.linguistic_versatility.evaluate_response import ALLOWED_MIME_TYPES

_gemini_service = GeminiVersatilityService()


async def evaluate_free_versatility_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    audio_bytes: bytes,
    mime_type: str,
) -> tuple[LinguisticVersatilitySession, LinguisticVersatilityRound]:
    """Create a free-mode session, evaluate it, and finalize it in one shot.

    Free mode has exactly one round (the whole free-form recording), no
    question_id, and the session is closed immediately so it shows up in
    history with its result already attached.
    """
    safe_mime = mime_type if mime_type in ALLOWED_MIME_TYPES else "audio/webm"

    result = await _gemini_service.evaluate_free(audio_bytes, safe_mime)

    now = datetime.now(timezone.utc)
    intelligible = bool(result["audio_intelligible"])

    session = LinguisticVersatilitySession(
        user_id=user_id,
        mode="free",
        total_rounds=1,
        completed_rounds=1 if intelligible else 0,
        status="completed",
        completed_at=now,
        overall_score=result["versatility_score"] if intelligible else None,
    )
    db.add(session)
    await db.flush()

    round_entity = LinguisticVersatilityRound(
        session_id=session.id,
        question_id=None,
        question_text=None,
        audio_intelligible=intelligible,
    )
    if intelligible:
        round_entity.versatility_score = result["versatility_score"]
        round_entity.vocabulary_richness = result["vocabulary_richness"]
        round_entity.feedback = result["feedback"]

    db.add(round_entity)
    await db.flush()
    return session, round_entity
