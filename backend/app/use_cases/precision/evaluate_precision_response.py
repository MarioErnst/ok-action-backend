import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.precision_round import PrecisionRound
from app.domain.entities.precision_session import PrecisionSession
from app.infrastructure.ai.precision_gemini import GeminiPrecisionService, PrecisionGeminiError

_gemini_service = GeminiPrecisionService()

ALLOWED_MIME_TYPES = {"audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/mpeg"}


def calculate_overall_score(relevance: int, directness: int, conciseness: int) -> int:
    return round((relevance * 0.4) + (directness * 0.3) + (conciseness * 0.3))


async def evaluate_precision_response(
    db: AsyncSession,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    question_text: str,
    audio_bytes: bytes,
    mime_type: str,
    noise_level: str,
    audio_duration_secs: float | None = None,
) -> PrecisionRound:
    # question_text must be provided by the caller as a snapshot; it is not fetched from DB here.
    safe_mime = mime_type if mime_type in ALLOWED_MIME_TYPES else "audio/webm"

    result = await _gemini_service.evaluate_response(
        audio_bytes, safe_mime, question_text, noise_level
    )

    round_entity = PrecisionRound(
        id=uuid.uuid4(),
        session_id=session_id,
        question_id=question_id,
        question_text=question_text,
        audio_duration_secs=audio_duration_secs,
        noise_level=noise_level,
        audio_intelligible=result["audio_intelligible"],
        created_at=datetime.now(timezone.utc),
    )

    if result["audio_intelligible"]:
        round_entity.transcript = result["transcript"]
        round_entity.relevance_score = result["relevance_score"]
        round_entity.directness_score = result["directness_score"]
        round_entity.conciseness_score = result["conciseness_score"]
        round_entity.overall_score = calculate_overall_score(
            result["relevance_score"], result["directness_score"], result["conciseness_score"]
        )
        round_entity.feedback = result["feedback"]
        round_entity.strengths = result["strengths"]
        round_entity.improvement_areas = result["improvement_areas"]

        # Increment completed_rounds on session
        session = await db.get(PrecisionSession, session_id)
        if session:
            session.completed_rounds += 1

    db.add(round_entity)
    await db.flush()
    return round_entity
