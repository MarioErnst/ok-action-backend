from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import StopReasonEnum
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.ai.composed_live_gemini import evaluate_composed_audio
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.live import (
    AbandonSessionRequest,
    ComposedAudioEvaluationResponse,
    FacialSummaryInput,
    FinalizeSessionResponse,
    LiveChildOutput,
    LiveMetricsOutput,
    LiveSessionDetail,
    LiveSessionListItem,
    StartSessionResponse,
)
from app.use_cases.live.composed.persist import persist_composed_evaluation
from app.use_cases.live.composed.prompts import VALID_MODULES, ComposableModule
from app.use_cases.live.sessions import (
    InvalidParentLiveError,
    SessionNotActiveError,
    SessionNotFoundError,
    abandon_live_session,
    finalize_live_session,
    get_live_session,
    list_live_sessions,
    start_live_session,
    validate_parent_live_session,
)

router = APIRouter(prefix="/live", tags=["live"])


@router.post(
    "/sessions",
    response_model=StartSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_session_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> StartSessionResponse:
    """Open an active live session.

    Returns the session_id the client uses both for finalize/abandon and
    (once child modules accept parent_id) as the parent_id when creating
    component module sessions inside this composition.
    """

    session_row = await start_live_session(db=db, user=user)
    return StartSessionResponse(
        session_id=session_row.id, started_at=session_row.started_at
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
        session_row, _ = await finalize_live_session(
            db=db, user=user, session_id=session_id
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión live no encontrada",
        )
    except SessionNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )

    children_count = (
        await db.execute(
            select(func.count(Session.id)).where(Session.parent_id == session_id)
        )
    ).scalar_one()
    return FinalizeSessionResponse(
        session_id=session_row.id,
        status="completed",
        score=session_row.score,
        children_count=int(children_count),
    )


@router.patch(
    "/sessions/{session_id}/abandon",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def abandon_session_endpoint(
    session_id: UUID,
    payload: AbandonSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    try:
        await abandon_live_session(
            db=db,
            user=user,
            session_id=session_id,
            stop_reason=StopReasonEnum(payload.stop_reason),
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión live no encontrada",
        )
    except SessionNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )


@router.get("/sessions", response_model=list[LiveSessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[LiveSessionListItem]:
    rows = await list_live_sessions(db=db, user=user)
    return [
        LiveSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            children_count=children_count,
            stop_reason=stop_reason,
        )
        for session_row, children_count, stop_reason in rows
    ]


@router.post(
    "/sessions/{session_id}/audio-evaluation",
    response_model=ComposedAudioEvaluationResponse,
)
async def evaluate_audio_endpoint(
    session_id: UUID,
    audio: UploadFile,
    modules: list[str] = Form(...),
    started_at: datetime = Form(...),
    prompt_text: str = Form(""),
    facial_summary: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ComposedAudioEvaluationResponse:
    """Single Gemini call evaluating one audio against several modules.

    The request is multipart so the client can send the recorded blob
    alongside the module list. modules is a repeated form field
    (modules=muletillas&modules=facial_expression&...). started_at is the
    client-side timestamp from when MediaRecorder began; we trust it for
    the child sessions because the user could only lie about their own
    duration. ended_at is set server-side to now() for honesty.

    facial_summary is an optional JSON-encoded payload containing the
    seven emotion percentages computed in the browser. It is required
    only when facial_expression is among the selected modules; otherwise
    it is ignored.
    """

    if not modules:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one module is required",
        )
    invalid = [m for m in modules if m not in VALID_MODULES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid module(s): {invalid}",
        )

    composable_modules = cast(list[ComposableModule], modules)

    facial_summary_payload: dict | None = None
    if "facial_expression" in composable_modules:
        if not facial_summary:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="facial_summary is required when facial_expression is selected",
            )
        try:
            parsed = FacialSummaryInput.model_validate_json(facial_summary)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid facial_summary payload: {exc}",
            )
        facial_summary_payload = parsed.model_dump()

    try:
        await validate_parent_live_session(db, user, session_id)
    except InvalidParentLiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Audio is empty",
        )
    mime_type = audio.content_type or "audio/webm"

    gemini_response = await evaluate_composed_audio(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        modules=composable_modules,
        prompt_text=prompt_text or None,
    )
    if gemini_response is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo evaluar el audio con Gemini",
        )

    ended_at = datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    created = await persist_composed_evaluation(
        db=db,
        user=user,
        parent_live_id=session_id,
        started_at=started_at,
        ended_at=ended_at,
        modules=composable_modules,
        gemini_response=gemini_response,
        facial_summary=facial_summary_payload,
    )

    return ComposedAudioEvaluationResponse(
        audio_intelligible=bool(gemini_response.get("audio_intelligible")),
        children=[
            LiveChildOutput(
                id=session_row.id,
                module=session_row.module.value,
                started_at=session_row.started_at,
                ended_at=session_row.ended_at,
                duration_ms=session_row.duration_ms,
                score=session_row.score,
                status=session_row.status,
            )
            for session_row, _ in created
        ],
        evaluation=gemini_response,
    )


@router.get("/sessions/{session_id}", response_model=LiveSessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> LiveSessionDetail:
    found = await get_live_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión live no encontrada",
        )
    session_row, metrics_row, children = found
    return LiveSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=LiveMetricsOutput.model_validate(metrics_row) if metrics_row else None,
        children=[
            LiveChildOutput(
                id=child.id,
                module=child.module.value,
                started_at=child.started_at,
                ended_at=child.ended_at,
                duration_ms=child.duration_ms,
                score=child.score,
                status=child.status,
            )
            for child in children
        ],
    )
