from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.accentuation_metrics import AccentuationMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.ai.gemini import GeminiEvaluationError
from app.infrastructure.audio.mime import verify_audio_mime
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.accentuation import (
    AccentuationMetricsOutput,
    AccentuationSessionCreate,
    AccentuationSessionDetail,
    AccentuationSessionListItem,
    PhraseEvaluation,
    PhraseSpecificError,
)
from app.use_cases.accentuation.evaluate_phrase import evaluate_phrase
from app.use_cases.accentuation.sessions import (
    create_accentuation_session,
    get_accentuation_session,
    list_accentuation_sessions,
)
from app.use_cases.live.sessions import InvalidParentLiveError

router = APIRouter(prefix="/accentuation", tags=["accentuation"])


def _build_detail(
    session_row: Session, metrics_row: AccentuationMetrics
) -> AccentuationSessionDetail:
    return AccentuationSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=AccentuationMetricsOutput.model_validate(metrics_row),
    )


@router.post("/evaluate", response_model=PhraseEvaluation)
async def evaluate_phrase_endpoint(
    audio: UploadFile,
    phrase_text: str = Form(...),
    phrase_index: int = Form(...),
    user: User = Depends(get_current_user),
) -> PhraseEvaluation:
    """Score a single phrase via Gemini.

    The response carries Gemini's per-phrase feedback and specific_errors
    for ephemeral display in the UI; none of that is persisted to the DB.
    The frontend aggregates phrase scores and posts /sessions to record
    the session's aggregated metrics.
    """

    mime_type = verify_audio_mime(audio)
    audio_bytes = await audio.read()

    try:
        evaluation = await evaluate_phrase(audio_bytes, mime_type, phrase_text)
    except GeminiEvaluationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
        )

    return PhraseEvaluation(
        phrase_text=phrase_text,
        phrase_index=phrase_index,
        overall_score=evaluation["overall_score"],
        pronunciation_score=evaluation["pronunciation_score"],
        rhythm_score=evaluation["rhythm_score"],
        intonation_score=evaluation["intonation_score"],
        stress_score=evaluation["stress_score"],
        feedback=evaluation["feedback"],
        specific_errors=[
            PhraseSpecificError(**error_item)
            for error_item in evaluation.get("specific_errors", [])
        ],
    )


@router.post(
    "/sessions",
    response_model=AccentuationSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    payload: AccentuationSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> AccentuationSessionDetail:
    try:
        session_row, metrics_row = await create_accentuation_session(
            db=db, user=user, payload=payload
        )
    except InvalidParentLiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return _build_detail(session_row, metrics_row)


@router.get("/sessions", response_model=list[AccentuationSessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[AccentuationSessionListItem]:
    rows = await list_accentuation_sessions(db=db, user=user)
    return [
        AccentuationSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            phrases_count=metrics_row.phrases_count,
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=AccentuationSessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> AccentuationSessionDetail:
    found = await get_accentuation_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de acentuación no encontrada",
        )
    return _build_detail(*found)
