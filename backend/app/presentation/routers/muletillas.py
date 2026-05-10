from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.muletillas_metrics import MuletillasMetrics
from app.domain.entities.muletillas_word_usage import MuletillasWordUsage
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.ai.muletillas_gemini import GeminiMuletillasError
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.muletillas import (
    MuletillaDetectedEphemeral,
    MuletillaWordOutput,
    MuletillasEvaluationResponse,
    MuletillasMetricsOutput,
    MuletillasSessionCreate,
    MuletillasSessionDetail,
    MuletillasSessionListItem,
    RandomQuestionResponse,
)
from app.use_cases.muletillas.evaluate_response import (
    evaluate_response,
    get_random_question,
)
from app.use_cases.muletillas.sessions import (
    DuplicateMuletillaWordError,
    create_muletillas_session,
    get_muletillas_session,
    list_muletillas_sessions,
)

router = APIRouter(prefix="/muletillas", tags=["muletillas"])


def _build_detail(
    session_row: Session,
    metrics_row: MuletillasMetrics,
    word_rows: list[MuletillasWordUsage],
) -> MuletillasSessionDetail:
    return MuletillasSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=MuletillasMetricsOutput.model_validate(metrics_row),
        words=[MuletillaWordOutput.model_validate(w) for w in word_rows],
    )


@router.get("/questions/random", response_model=RandomQuestionResponse)
async def get_random_question_endpoint(
    user: User = Depends(get_current_user),
) -> RandomQuestionResponse:
    """Return a random open-ended question.

    Currently backed by a hardcoded list in the use_case; migration to the
    unified prompts catalog (with module='muletillas') is pending.
    """

    return RandomQuestionResponse(question=get_random_question())


@router.post("/evaluate", response_model=MuletillasEvaluationResponse)
async def evaluate_endpoint(
    audio: UploadFile,
    question_text: str = Form(...),
    user: User = Depends(get_current_user),
) -> MuletillasEvaluationResponse:
    """Evaluate a recorded answer with Gemini.

    The response carries Gemini's feedback, strengths, improvement_areas,
    overall/muletillas score and the per-word suggestion text for ephemeral
    display in the UI; only the aggregate metrics and per-word counts make
    it to the DB via /sessions.
    """

    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"

    try:
        evaluation = await evaluate_response(audio_bytes, mime_type, question_text)
    except GeminiMuletillasError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
        )

    return MuletillasEvaluationResponse(
        overall_score=evaluation["overall_score"],
        fluency_score=evaluation["fluency_score"],
        muletillas_score=evaluation["muletillas_score"],
        total_muletillas_count=evaluation["total_muletillas_count"],
        muletillas_per_minute=evaluation["muletillas_per_minute"],
        muletillas_detected=[
            MuletillaDetectedEphemeral(**m)
            for m in evaluation.get("muletillas_detected", [])
        ],
        feedback=evaluation["feedback"],
        strengths=evaluation["strengths"],
        improvement_areas=evaluation["improvement_areas"],
    )


@router.post(
    "/sessions",
    response_model=MuletillasSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    payload: MuletillasSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> MuletillasSessionDetail:
    try:
        session_row, metrics_row, word_rows = await create_muletillas_session(
            db=db, user=user, payload=payload
        )
    except DuplicateMuletillaWordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return _build_detail(session_row, metrics_row, word_rows)


@router.get("/sessions", response_model=list[MuletillasSessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[MuletillasSessionListItem]:
    rows = await list_muletillas_sessions(db=db, user=user)
    return [
        MuletillasSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            muletillas_count=metrics_row.muletillas_count,
            fluency_score=metrics_row.fluency_score,
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=MuletillasSessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> MuletillasSessionDetail:
    found = await get_muletillas_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de muletillas no encontrada",
        )
    return _build_detail(*found)
