# Full module documentation: documentacion/modulos/versatilidad-linguistica.md
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.linguistic_versatility_question import (
    LinguisticVersatilityQuestion as QuestionEntity,
)
from app.domain.entities.linguistic_versatility_session import (
    LinguisticVersatilitySession,
)
from app.domain.entities.user import User
from app.infrastructure.ai.linguistic_versatility_gemini import (
    VersatilityGeminiError,
)
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.linguistic_versatility import (
    EvaluateRoundResponse,
    FreeSessionResponse,
    QuestionSchema,
    RoundResultResponse,
    SessionDetailResponse,
    SessionListItem,
    StartSessionResponse,
)
from app.use_cases.linguistic_versatility.abandon_session import (
    abandon_versatility_session,
)
from app.use_cases.linguistic_versatility.evaluate_free import (
    evaluate_free_versatility_session,
)
from app.use_cases.linguistic_versatility.evaluate_response import (
    evaluate_versatility_response,
)
from app.use_cases.linguistic_versatility.finalize_session import (
    finalize_versatility_session,
)
from app.use_cases.linguistic_versatility.get_history import get_versatility_history
from app.use_cases.linguistic_versatility.get_session import get_versatility_session
from app.use_cases.linguistic_versatility.start_session import start_versatility_session

# Cap to mirror the schema constant (5 MB). Read here so the router rejects
# oversized uploads before they hit Gemini and burn tokens.
MAX_AUDIO_BYTES = 5 * 1024 * 1024

router = APIRouter(prefix="/linguistic-versatility", tags=["linguistic-versatility"])


def _round_to_response(r) -> RoundResultResponse:
    return RoundResultResponse(
        id=str(r.id),
        question_id=str(r.question_id) if r.question_id else None,
        question_text=r.question_text,
        versatility_score=r.versatility_score,
        vocabulary_richness=r.vocabulary_richness,
        feedback=r.feedback,
        audio_intelligible=r.audio_intelligible,
        created_at=r.created_at.isoformat(),
    )


@router.post("/sessions", response_model=StartSessionResponse, status_code=201)
async def start_session(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Open a guided session and return the questions the user must answer."""
    try:
        session, questions = await start_versatility_session(db, user_id=user.id)
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return StartSessionResponse(
        session_id=str(session.id),
        total_rounds=session.total_rounds,
        questions=[
            QuestionSchema(
                id=str(q.id),
                text=q.text,
                category=q.category,
                difficulty_level=q.difficulty_level,
            )
            for q in questions
        ],
    )


@router.post("/sessions/{session_id}/rounds", response_model=EvaluateRoundResponse)
async def evaluate_round(
    session_id: uuid.UUID,
    audio: UploadFile = File(...),
    question_id: str = Form(...),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Upload one answer audio and get its evaluation back."""
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio demasiado grande")
    mime_type = audio.content_type or "audio/webm"

    try:
        question_uuid = uuid.UUID(question_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")

    question = await db.get(QuestionEntity, question_uuid)
    if not question:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")

    try:
        round_entity = await evaluate_versatility_response(
            db=db,
            session_id=session_id,
            question_id=question_uuid,
            question_text=question.text,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
        )
    except VersatilityGeminiError as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        await db.rollback()
        raise

    # Re-read parent session so the response shows the freshest counters.
    session = await db.get(LinguisticVersatilitySession, session_id)
    await db.commit()

    return EvaluateRoundResponse(
        round_id=str(round_entity.id),
        audio_intelligible=round_entity.audio_intelligible,
        versatility_score=round_entity.versatility_score,
        vocabulary_richness=round_entity.vocabulary_richness,
        feedback=round_entity.feedback,
        completed_rounds=session.completed_rounds if session else 0,
        total_rounds=session.total_rounds if session else 0,
    )


@router.post("/sessions/{session_id}/finalize", response_model=SessionDetailResponse)
async def finalize_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Mark a session completed, compute its overall score, and return its detail."""
    session = await finalize_versatility_session(db, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    await db.commit()

    # Re-read with rounds for the response.
    full = await get_versatility_session(db, session_id, user.id)
    return SessionDetailResponse(
        id=str(full.id),
        mode=full.mode,
        total_rounds=full.total_rounds,
        completed_rounds=full.completed_rounds,
        overall_score=full.overall_score,
        status=full.status,
        created_at=full.created_at.isoformat(),
        completed_at=full.completed_at.isoformat() if full.completed_at else None,
        rounds=[_round_to_response(r) for r in full.rounds],
    )


@router.patch("/sessions/{session_id}/abandon", status_code=204)
async def abandon_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Mark a session as abandoned. Idempotent: missing session returns 204 too
    so the client can fire-and-forget on navigation away."""
    session = await abandon_versatility_session(db, session_id)
    if session and session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    await db.commit()


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Return the full detail of a session including all rounds."""
    session = await get_versatility_session(db, session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return SessionDetailResponse(
        id=str(session.id),
        mode=session.mode,
        total_rounds=session.total_rounds,
        completed_rounds=session.completed_rounds,
        overall_score=session.overall_score,
        status=session.status,
        created_at=session.created_at.isoformat(),
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        rounds=[_round_to_response(r) for r in session.rounds],
    )


@router.get("/history", response_model=list[SessionListItem])
async def history(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Return the user's session history newest first."""
    sessions = await get_versatility_history(db, user.id)
    return [
        SessionListItem(
            id=str(s.id),
            mode=s.mode,
            overall_score=s.overall_score,
            status=s.status,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.post("/free", response_model=FreeSessionResponse, status_code=201)
async def free_session(
    audio: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Free-mode session in one shot: upload one audio, get one analysis."""
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio demasiado grande")
    mime_type = audio.content_type or "audio/webm"

    try:
        session, round_entity = await evaluate_free_versatility_session(
            db, user_id=user.id, audio_bytes=audio_bytes, mime_type=mime_type
        )
    except VersatilityGeminiError as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        await db.rollback()
        raise

    await db.commit()
    return FreeSessionResponse(
        session_id=str(session.id),
        versatility_score=round_entity.versatility_score,
        vocabulary_richness=round_entity.vocabulary_richness,
        feedback=round_entity.feedback,
        audio_intelligible=round_entity.audio_intelligible,
    )
