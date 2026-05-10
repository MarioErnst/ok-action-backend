from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum
from app.domain.entities.precision_metrics import PrecisionMetrics
from app.domain.entities.precision_round import PrecisionRound
from app.domain.entities.prompt import Prompt
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.ai.precision_gemini import (
    GeminiPrecisionService,
    PrecisionGeminiError,
)
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.precision import (
    EvaluateRoundResponse,
    FinalizeSessionResponse,
    PrecisionMetricsOutput,
    PrecisionRoundOutput,
    PrecisionSessionDetail,
    PrecisionSessionListItem,
    PromptOut,
    StartSessionRequest,
    StartSessionResponse,
)
from app.use_cases.precision.sessions import (
    NotEnoughPromptsError,
    PromptNotAvailableError,
    SessionNotActiveError,
    SessionNotFoundError,
    abandon_precision_session,
    evaluate_round,
    finalize_precision_session,
    get_precision_session,
    list_precision_sessions,
    start_precision_session,
)

router = APIRouter(prefix="/precision", tags=["precision"])

_gemini = GeminiPrecisionService()


def _build_detail(
    session_row: Session,
    metrics_row: PrecisionMetrics,
    round_rows: list[PrecisionRound],
) -> PrecisionSessionDetail:
    return PrecisionSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=PrecisionMetricsOutput.model_validate(metrics_row),
        rounds=[PrecisionRoundOutput.model_validate(r) for r in round_rows],
    )


@router.post(
    "/sessions",
    response_model=StartSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_session_endpoint(
    payload: StartSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> StartSessionResponse:
    try:
        session_row, _, prompts = await start_precision_session(
            db=db, user=user, rounds_total=payload.rounds_total
        )
    except NotEnoughPromptsError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )

    return StartSessionResponse(
        session_id=session_row.id,
        started_at=session_row.started_at,
        rounds_total=payload.rounds_total,
        prompts=[PromptOut.model_validate(p) for p in prompts],
    )


@router.post(
    "/sessions/{session_id}/rounds",
    response_model=EvaluateRoundResponse,
)
async def evaluate_round_endpoint(
    session_id: UUID,
    audio: UploadFile,
    round_index: int = Form(..., ge=0),
    prompt_id: UUID = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> EvaluateRoundResponse:
    """Evaluate the user's audio answer for one round of the session.

    The router orchestrates the Gemini call (it owns the HTTP/audio boundary)
    so the use_case only consumes the parsed evaluation dict. Returns
    Gemini's transcript and feedback text for ephemeral display in the UI;
    persistence keeps only scores and is_audio_intelligible.
    """

    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"

    # Fetch the prompt text up front so a missing/inactive prompt fails with
    # 422 here instead of leaking through Gemini as a 502. The use_case
    # re-checks the prompt for its own invariants (module, active) — the two
    # queries are cheap and keep router and use_case responsibilities clean.
    prompt_row = (
        await db.execute(
            select(Prompt).where(
                Prompt.id == prompt_id,
                Prompt.module == ModuleEnum.precision,
                Prompt.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if prompt_row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"prompt {prompt_id} not found or not available for precision",
        )

    try:
        evaluation = await _gemini.evaluate_response(
            audio_bytes, mime_type, prompt_row.text
        )
    except PrecisionGeminiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        )

    try:
        round_row = await evaluate_round(
            db=db,
            user=user,
            session_id=session_id,
            round_index=round_index,
            prompt_id=prompt_id,
            gemini_evaluation=evaluation,
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de precisión no encontrada",
        )
    except SessionNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    except PromptNotAvailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    return EvaluateRoundResponse(
        round_index=round_row.round_index,
        prompt_id=round_row.prompt_id,
        is_audio_intelligible=round_row.is_audio_intelligible,
        score=round_row.score,
        relevance_score=round_row.relevance_score,
        directness_score=round_row.directness_score,
        conciseness_score=round_row.conciseness_score,
        transcript=evaluation.get("transcript", ""),
        feedback=evaluation.get("feedback", ""),
        strengths=evaluation.get("strengths", []),
        improvement_areas=evaluation.get("improvement_areas", []),
    )


@router.post(
    "/sessions/{session_id}/finalize",
    response_model=FinalizeSessionResponse,
)
async def finalize_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> FinalizeSessionResponse:
    try:
        session_row, metrics_row = await finalize_precision_session(
            db=db, user=user, session_id=session_id
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de precisión no encontrada",
        )
    except SessionNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )

    return FinalizeSessionResponse(
        session_id=session_row.id,
        status=session_row.status,
        score=session_row.score,
        rounds_completed=metrics_row.rounds_completed,
        rounds_total=metrics_row.rounds_total,
        relevance_score=metrics_row.relevance_score,
        directness_score=metrics_row.directness_score,
        conciseness_score=metrics_row.conciseness_score,
    )


@router.patch(
    "/sessions/{session_id}/abandon",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def abandon_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    try:
        await abandon_precision_session(db=db, user=user, session_id=session_id)
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de precisión no encontrada",
        )
    except SessionNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )


@router.get("/sessions", response_model=list[PrecisionSessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[PrecisionSessionListItem]:
    rows = await list_precision_sessions(db=db, user=user)
    return [
        PrecisionSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            rounds_total=metrics_row.rounds_total,
            rounds_completed=metrics_row.rounds_completed,
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=PrecisionSessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> PrecisionSessionDetail:
    found = await get_precision_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de precisión no encontrada",
        )
    return _build_detail(*found)
