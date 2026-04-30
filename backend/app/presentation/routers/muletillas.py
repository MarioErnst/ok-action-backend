from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.ai.muletillas_gemini import GeminiMuletillasError
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.muletillas import (
    MuletillaDetectedSchema,
    MuletillasEvaluationResponse,
    MuletillasSessionListItem,
    MuletillasSessionRequest,
    MuletillasSessionResponse,
    RandomQuestionResponse,
)
import app.use_cases.muletillas.evaluate_response as evaluate_response_module
from app.use_cases.muletillas.sessions import (
    get_muletillas_session,
    list_muletillas_sessions,
    save_muletillas_session,
)

router = APIRouter(prefix="/muletillas", tags=["muletillas"])

ALLOWED_AUDIO_MIME_TYPES = {"audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/mpeg"}


@router.get("/questions/random", response_model=RandomQuestionResponse)
async def get_random_question(
    user: User = Depends(get_current_user),
):
    question = evaluate_response_module.get_random_question()
    return RandomQuestionResponse(question=question)


@router.post("/evaluate", response_model=MuletillasEvaluationResponse)
async def evaluate_endpoint(
    audio: UploadFile,
    question_text: str = Form(...),
    user: User = Depends(get_current_user),
):
    audio_bytes = await audio.read()
    mime_type = audio.content_type if audio.content_type in ALLOWED_AUDIO_MIME_TYPES else "audio/webm"

    try:
        evaluation = await evaluate_response_module.evaluate_response(
            audio_bytes, mime_type, question_text
        )
    except GeminiMuletillasError as error:
        raise HTTPException(status_code=502, detail=str(error))

    return MuletillasEvaluationResponse(
        overall_score=evaluation["overall_score"],
        fluency_score=evaluation["fluency_score"],
        muletillas_score=evaluation["muletillas_score"],
        total_muletillas_count=evaluation["total_muletillas_count"],
        muletillas_per_minute=evaluation["muletillas_per_minute"],
        muletillas_detected=[
            MuletillaDetectedSchema(**m) for m in evaluation.get("muletillas_detected", [])
        ],
        feedback=evaluation["feedback"],
        strengths=evaluation["strengths"],
        improvement_areas=evaluation["improvement_areas"],
    )


@router.post("/sessions", response_model=MuletillasSessionResponse, status_code=201)
async def create_session(
    request: MuletillasSessionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    muletillas_session = await save_muletillas_session(
        data=request.model_dump(),
        user=user,
        session=session,
    )

    result = await get_muletillas_session(str(muletillas_session.id), user, session)
    if not result:
        raise HTTPException(status_code=500, detail="Error al recuperar la sesion creada")

    return MuletillasSessionResponse(
        id=str(result.id),
        question_text=result.question_text,
        overall_score=float(result.overall_score),
        fluency_score=float(result.fluency_score),
        muletillas_score=float(result.muletillas_score),
        total_muletillas_count=result.total_muletillas_count,
        muletillas_per_minute=float(result.muletillas_per_minute),
        feedback=result.feedback,
        strengths=result.strengths,
        improvement_areas=result.improvement_areas,
        created_at=result.created_at.isoformat(),
        muletillas_detected=[
            MuletillaDetectedSchema(
                word=m.word,
                count=m.count,
                severity=m.severity,
                suggestion=m.suggestion,
            )
            for m in result.muletillas_detected
        ],
    )


@router.get("/sessions", response_model=list[MuletillasSessionResponse])
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    sessions = await list_muletillas_sessions(user, session)
    return [
        MuletillasSessionListItem(
            id=str(s.id),
            question_text=s.question_text,
            overall_score=float(s.overall_score),
            total_muletillas_count=s.total_muletillas_count,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=MuletillasSessionResponse)
async def get_session_detail(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await get_muletillas_session(session_id, user, session)
    if not result:
        raise HTTPException(status_code=404, detail="Sesion no encontrada")

    return MuletillasSessionResponse(
        id=str(result.id),
        question_text=result.question_text,
        overall_score=float(result.overall_score),
        fluency_score=float(result.fluency_score),
        muletillas_score=float(result.muletillas_score),
        total_muletillas_count=result.total_muletillas_count,
        muletillas_per_minute=float(result.muletillas_per_minute),
        feedback=result.feedback,
        strengths=result.strengths,
        improvement_areas=result.improvement_areas,
        created_at=result.created_at.isoformat(),
        muletillas_detected=[
            MuletillaDetectedSchema(
                word=m.word,
                count=m.count,
                severity=m.severity,
                suggestion=m.suggestion,
            )
            for m in result.muletillas_detected
        ],
    )
