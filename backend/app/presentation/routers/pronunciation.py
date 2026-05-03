# Documentacion detallada de este modulo: documentacion/modulos/pronunciacion.md
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.ai.pronunciation_gemini import GeminiPronunciationError
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.pronunciation import (
    PhonemeErrorSchema,
    PhrasePronunciationResponse,
    PronunciationSessionListItem,
    PronunciationSessionRequest,
    PronunciationSessionResponse,
)
import app.use_cases.pronunciation.evaluate_phrase as evaluate_phrase_module
from app.use_cases.pronunciation.sessions import (
    get_pronunciation_session,
    list_pronunciation_sessions,
    save_pronunciation_session,
)

router = APIRouter(prefix="/pronunciation", tags=["pronunciation"])

ALLOWED_AUDIO_MIME_TYPES = {"audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/mpeg"}


@router.post("/evaluate", response_model=PhrasePronunciationResponse)
async def evaluate_phrase_endpoint(
    audio: UploadFile,
    phrase_text: str = Form(...),
    phrase_index: int = Form(...),
    level: str = Form(...),
    user: User = Depends(get_current_user),
):
    audio_bytes = await audio.read()
    mime_type = audio.content_type if audio.content_type in ALLOWED_AUDIO_MIME_TYPES else "audio/webm"

    try:
        evaluation = await evaluate_phrase_module.evaluate_phrase(audio_bytes, mime_type, phrase_text, level)
    except GeminiPronunciationError as error:
        raise HTTPException(status_code=502, detail=str(error))

    return PhrasePronunciationResponse(
        phrase_text=phrase_text,
        phrase_index=phrase_index,
        overall_score=evaluation["overall_score"],
        vowel_score=evaluation["vowel_score"],
        consonant_score=evaluation["consonant_score"],
        fluency_score=evaluation["fluency_score"],
        intelligibility_score=evaluation["intelligibility_score"],
        feedback=evaluation["feedback"],
        phoneme_errors=[
            PhonemeErrorSchema(**error_item)
            for error_item in evaluation.get("phoneme_errors", [])
        ],
    )


@router.post("/sessions", response_model=PronunciationSessionResponse, status_code=201)
async def create_session(
    request: PronunciationSessionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    pronunciation_session = await save_pronunciation_session(
        data=request.model_dump(),
        user=user,
        session=session,
    )

    result = await get_pronunciation_session(str(pronunciation_session.id), user, session)
    if not result:
        raise HTTPException(status_code=500, detail="Error al recuperar la sesion creada")

    return PronunciationSessionResponse(
        id=str(result.id),
        level=result.level,
        overall_score=float(result.overall_score),
        vowel_score=float(result.vowel_score),
        consonant_score=float(result.consonant_score),
        fluency_score=float(result.fluency_score),
        intelligibility_score=float(result.intelligibility_score),
        summary_feedback=result.summary_feedback,
        created_at=result.created_at.isoformat(),
        evaluations=[
            PhrasePronunciationResponse(
                phrase_text=ev.phrase_text,
                phrase_index=ev.phrase_index,
                overall_score=float(ev.overall_score),
                vowel_score=float(ev.vowel_score),
                consonant_score=float(ev.consonant_score),
                fluency_score=float(ev.fluency_score),
                intelligibility_score=float(ev.intelligibility_score),
                feedback=ev.feedback,
                phoneme_errors=[
                    PhonemeErrorSchema(**error_item)
                    for error_item in ev.phoneme_errors
                ],
            )
            for ev in result.phrase_pronunciations
        ],
    )


@router.get("/sessions", response_model=list[PronunciationSessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    sessions = await list_pronunciation_sessions(user, session)
    return [
        PronunciationSessionListItem(
            id=str(s.id),
            level=s.level,
            overall_score=float(s.overall_score),
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=PronunciationSessionResponse)
async def get_session_detail(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await get_pronunciation_session(session_id, user, session)
    if not result:
        raise HTTPException(status_code=404, detail="Sesion no encontrada")

    return PronunciationSessionResponse(
        id=str(result.id),
        level=result.level,
        overall_score=float(result.overall_score),
        vowel_score=float(result.vowel_score),
        consonant_score=float(result.consonant_score),
        fluency_score=float(result.fluency_score),
        intelligibility_score=float(result.intelligibility_score),
        summary_feedback=result.summary_feedback,
        created_at=result.created_at.isoformat(),
        evaluations=[
            PhrasePronunciationResponse(
                phrase_text=ev.phrase_text,
                phrase_index=ev.phrase_index,
                overall_score=float(ev.overall_score),
                vowel_score=float(ev.vowel_score),
                consonant_score=float(ev.consonant_score),
                fluency_score=float(ev.fluency_score),
                intelligibility_score=float(ev.intelligibility_score),
                feedback=ev.feedback,
                phoneme_errors=[
                    PhonemeErrorSchema(**error_item)
                    for error_item in ev.phoneme_errors
                ],
            )
            for ev in result.phrase_pronunciations
        ],
    )
