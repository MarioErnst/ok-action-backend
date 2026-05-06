# Full module documentation: documentacion/modulos/precision.md
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.ai.precision_gemini import PrecisionGeminiError
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.precision import (
    EvaluateRoundResponse,
    FinalizeSessionResponse,
    PrecisionHistoryItem,
    PrecisionQuestionSchema,
    PrecisionRoundResponse,
    PrecisionSessionResponse,
    StartSessionResponse,
)
from app.use_cases.precision.start_precision_session import start_precision_session
from app.use_cases.precision.evaluate_precision_response import evaluate_precision_response
from app.use_cases.precision.finalize_precision_session import finalize_precision_session
from app.use_cases.precision.abandon_precision_session import abandon_precision_session
from app.use_cases.precision.get_precision_session import get_precision_session
from app.use_cases.precision.get_precision_history import get_precision_history

router = APIRouter(prefix="/precision", tags=["precision"])

ALLOWED_MIME_TYPES = {"audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/mpeg"}


@router.post("/sessions", response_model=StartSessionResponse)
async def start_session(
    total_rounds: int = 5,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    async with db.begin():
        session, questions = await start_precision_session(
            db, user_id=user.id, total_rounds=total_rounds
        )
    return StartSessionResponse(
        session_id=str(session.id),
        questions=[
            PrecisionQuestionSchema(
                id=str(q.id),
                text=q.text,
                category=q.category,
                difficulty_level=q.difficulty_level,
            )
            for q in questions
        ],
        total_rounds=session.total_rounds,
    )


@router.post("/sessions/{session_id}/rounds", response_model=EvaluateRoundResponse)
async def evaluate_round(
    session_id: uuid.UUID,
    audio: UploadFile = File(...),
    question_id: str = Form(...),
    noise_level: str = Form(default="low"),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    audio_bytes = await audio.read()
    mime_type = audio.content_type if audio.content_type in ALLOWED_MIME_TYPES else "audio/webm"

    try:
        async with db.begin():
            from app.domain.entities.precision_question import PrecisionQuestion as PQEntity
            q_result = await db.get(PQEntity, uuid.UUID(question_id))
            if not q_result:
                raise HTTPException(status_code=404, detail="Question not found")

            precision_round = await evaluate_precision_response(
                db=db,
                session_id=session_id,
                question_id=uuid.UUID(question_id),
                question_text=q_result.text,
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                noise_level=noise_level,
            )
    except PrecisionGeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return EvaluateRoundResponse(
        round_id=str(precision_round.id),
        audio_intelligible=precision_round.audio_intelligible,
        relevance_score=precision_round.relevance_score,
        directness_score=precision_round.directness_score,
        conciseness_score=precision_round.conciseness_score,
        overall_score=precision_round.overall_score,
        feedback=precision_round.feedback,
        strengths=precision_round.strengths,
        improvement_areas=precision_round.improvement_areas,
    )


@router.post("/sessions/{session_id}/finalize", response_model=FinalizeSessionResponse)
async def finalize_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    async with db.begin():
        session = await finalize_precision_session(db, session_id)
    return FinalizeSessionResponse(
        session_id=str(session.id),
        overall_score=float(session.overall_score) if session.overall_score is not None else None,
        completed_rounds=session.completed_rounds,
        status=session.status,
    )


@router.patch("/sessions/{session_id}/abandon", status_code=204)
async def abandon_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    async with db.begin():
        await abandon_precision_session(db, session_id)


@router.get("/sessions/{session_id}", response_model=PrecisionSessionResponse)
async def get_session_detail(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    session = await get_precision_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return PrecisionSessionResponse(
        id=str(session.id),
        mode=session.mode,
        total_rounds=session.total_rounds,
        completed_rounds=session.completed_rounds,
        overall_score=float(session.overall_score) if session.overall_score is not None else None,
        status=session.status,
        created_at=session.created_at.isoformat(),
        rounds=[
            PrecisionRoundResponse(
                id=str(r.id),
                question_text=r.question_text,
                relevance_score=r.relevance_score,
                directness_score=r.directness_score,
                conciseness_score=r.conciseness_score,
                overall_score=r.overall_score,
                feedback=r.feedback,
                strengths=r.strengths,
                improvement_areas=r.improvement_areas,
                noise_level=r.noise_level,
                audio_intelligible=r.audio_intelligible,
                created_at=r.created_at.isoformat(),
            )
            for r in session.rounds
        ],
    )


@router.get("/history", response_model=list[PrecisionHistoryItem])
async def history(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    sessions = await get_precision_history(db, user.id)
    return [
        PrecisionHistoryItem(
            id=str(s.id),
            overall_score=float(s.overall_score) if s.overall_score is not None else None,
            completed_rounds=s.completed_rounds,
            total_rounds=s.total_rounds,
            status=s.status,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]
