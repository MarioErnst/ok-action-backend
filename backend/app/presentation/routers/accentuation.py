# Documentacion detallada de este modulo: documentacion/modulos/acentuacion.md
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.ai.gemini import GeminiEvaluationError
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.accentuation import (
    AccentuationSessionListItem,
    AccentuationSessionRequest,
    AccentuationSessionResponse,
    PhraseEvaluationResponse,
    PhraseEvaluationRequest,
    SpecificErrorSchema,
)
from app.use_cases.accentuation.evaluate_phrase import evaluate_phrase
from app.use_cases.accentuation.sessions import (
    get_accentuation_session,
    list_accentuation_sessions,
    save_accentuation_session,
)

router = APIRouter(prefix="/accentuation", tags=["accentuation"])


@router.post("/evaluate", response_model=PhraseEvaluationResponse)
async def evaluate_phrase_endpoint(
    audio: UploadFile,
    phrase_text: str = Form(...),
    phrase_index: int = Form(...),
    user: User = Depends(get_current_user),
):
    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"

    try:
        evaluation = await evaluate_phrase(audio_bytes, mime_type, phrase_text)
    except GeminiEvaluationError as error:
        raise HTTPException(status_code=502, detail=str(error))

    return PhraseEvaluationResponse(
        phrase_text=phrase_text,
        phrase_index=phrase_index,
        overall_score=evaluation["overall_score"],
        pronunciation_score=evaluation["pronunciation_score"],
        rhythm_score=evaluation["rhythm_score"],
        intonation_score=evaluation["intonation_score"],
        stress_accuracy_score=evaluation["stress_accuracy_score"],
        feedback=evaluation["feedback"],
        specific_errors=[
            SpecificErrorSchema(**error_item)
            for error_item in evaluation.get("specific_errors", [])
        ],
    )


@router.post("/sessions", response_model=AccentuationSessionResponse, status_code=201)
async def create_session(
    request: AccentuationSessionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    accentuation_session = await save_accentuation_session(
        data=request.model_dump(),
        user=user,
        session=session,
    )

    result = await get_accentuation_session(str(accentuation_session.id), user, session)

    return AccentuationSessionResponse(
        id=str(result.id),
        overall_score=float(result.overall_score),
        pronunciation_score=float(result.pronunciation_score),
        rhythm_score=float(result.rhythm_score),
        intonation_score=float(result.intonation_score),
        stress_accuracy_score=float(result.stress_accuracy_score),
        summary_feedback=result.summary_feedback,
        created_at=result.created_at.isoformat(),
        evaluations=[
            PhraseEvaluationResponse(
                phrase_text=ev.phrase_text,
                phrase_index=ev.phrase_index,
                overall_score=float(ev.overall_score),
                pronunciation_score=float(ev.pronunciation_score),
                rhythm_score=float(ev.rhythm_score),
                intonation_score=float(ev.intonation_score),
                stress_accuracy_score=float(ev.stress_accuracy_score),
                feedback=ev.feedback,
                specific_errors=[
                    SpecificErrorSchema(**error_item)
                    for error_item in ev.specific_errors
                ],
            )
            for ev in result.phrase_evaluations
        ],
    )


@router.get("/sessions", response_model=list[AccentuationSessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    sessions = await list_accentuation_sessions(user, session)
    return [
        AccentuationSessionListItem(
            id=str(s.id),
            overall_score=float(s.overall_score),
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=AccentuationSessionResponse)
async def get_session_detail(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await get_accentuation_session(session_id, user, session)
    if not result:
        raise HTTPException(status_code=404, detail="Sesion no encontrada")

    return AccentuationSessionResponse(
        id=str(result.id),
        overall_score=float(result.overall_score),
        pronunciation_score=float(result.pronunciation_score),
        rhythm_score=float(result.rhythm_score),
        intonation_score=float(result.intonation_score),
        stress_accuracy_score=float(result.stress_accuracy_score),
        summary_feedback=result.summary_feedback,
        created_at=result.created_at.isoformat(),
        evaluations=[
            PhraseEvaluationResponse(
                phrase_text=ev.phrase_text,
                phrase_index=ev.phrase_index,
                overall_score=float(ev.overall_score),
                pronunciation_score=float(ev.pronunciation_score),
                rhythm_score=float(ev.rhythm_score),
                intonation_score=float(ev.intonation_score),
                stress_accuracy_score=float(ev.stress_accuracy_score),
                feedback=ev.feedback,
                specific_errors=[
                    SpecificErrorSchema(**error_item)
                    for error_item in ev.specific_errors
                ],
            )
            for ev in result.phrase_evaluations
        ],
    )
