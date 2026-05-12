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

from app.domain.entities.enums import (
    LinguisticVersatilityModeEnum,
    ModuleEnum,
)
from app.domain.entities.linguistic_versatility_metrics import (
    LinguisticVersatilityMetrics,
)
from app.domain.entities.linguistic_versatility_round import (
    LinguisticVersatilityRound,
)
from app.domain.entities.prompt import Prompt
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.ai.linguistic_versatility_gemini import (
    GeminiVersatilityService,
    VersatilityGeminiError,
)
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.linguistic_versatility import (
    EvaluateRoundResponse,
    FinalizeSessionResponse,
    LinguisticVersatilityMetricsOutput,
    LinguisticVersatilityRoundOutput,
    LinguisticVersatilitySessionDetail,
    LinguisticVersatilitySessionListItem,
    PromptOut,
    StartSessionRequest,
    StartSessionResponse,
)
from app.use_cases.linguistic_versatility.sessions import (
    NotEnoughPromptsError,
    PromptModeMismatchError,
    PromptNotAvailableError,
    RoundAlreadyEvaluatedError,
    RoundIndexOutOfRangeError,
    SessionNotActiveError,
    SessionNotFoundError,
    abandon_linguistic_versatility_session,
    evaluate_round,
    finalize_linguistic_versatility_session,
    get_linguistic_versatility_session,
    list_linguistic_versatility_sessions,
    start_linguistic_versatility_session,
)
from app.use_cases.live.sessions import InvalidParentLiveError

router = APIRouter(prefix="/linguistic-versatility", tags=["linguistic-versatility"])

_gemini = GeminiVersatilityService()


def _build_detail(
    session_row: Session,
    metrics_row: LinguisticVersatilityMetrics,
    round_rows: list[LinguisticVersatilityRound],
) -> LinguisticVersatilitySessionDetail:
    return LinguisticVersatilitySessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=LinguisticVersatilityMetricsOutput.model_validate(metrics_row),
        rounds=[
            LinguisticVersatilityRoundOutput.model_validate(r) for r in round_rows
        ],
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
        session_row, metrics_row, prompts = await start_linguistic_versatility_session(
            db=db,
            user=user,
            mode=LinguisticVersatilityModeEnum(payload.mode),
            rounds_total=payload.rounds_total,
            parent_id=payload.parent_id,
        )
    except NotEnoughPromptsError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    except InvalidParentLiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    return StartSessionResponse(
        session_id=session_row.id,
        started_at=session_row.started_at,
        mode=metrics_row.mode,
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
    prompt_id: UUID | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> EvaluateRoundResponse:
    """Evaluate one round.

    In guided mode the client must include prompt_id and the router fetches
    its text to give to Gemini. In free mode prompt_id must be omitted and
    the router calls Gemini's free evaluator. Use_case re-validates the
    pairing as an invariant.
    """

    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"

    # Look up the session mode up front so a guided/free pairing mismatch
    # fails with 422 before we burn a Gemini call. The use_case re-validates
    # the same invariants once the round persists.
    mode_row = (
        await db.execute(
            select(LinguisticVersatilityMetrics.mode)
            .join(Session, Session.id == LinguisticVersatilityMetrics.session_id)
            .where(
                Session.id == session_id,
                Session.module == ModuleEnum.linguistic_versatility,
                Session.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if mode_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de versatilidad no encontrada",
        )
    if mode_row == LinguisticVersatilityModeEnum.guided and prompt_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="prompt_id is required in guided mode",
        )
    if mode_row == LinguisticVersatilityModeEnum.free and prompt_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="prompt_id must be omitted in free mode",
        )

    prompt_text: str | None = None
    if prompt_id is not None:
        prompt_row = (
            await db.execute(
                select(Prompt).where(
                    Prompt.id == prompt_id,
                    Prompt.module == ModuleEnum.linguistic_versatility,
                    Prompt.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if prompt_row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"prompt {prompt_id} not found or not available for "
                f"linguistic_versatility",
            )
        prompt_text = prompt_row.text

    try:
        if prompt_text is not None:
            evaluation = await _gemini.evaluate_response(
                audio_bytes, mime_type, prompt_text
            )
        else:
            evaluation = await _gemini.evaluate_free(audio_bytes, mime_type)
    except VersatilityGeminiError as exc:
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
            detail="Sesión de versatilidad no encontrada",
        )
    except SessionNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    except RoundAlreadyEvaluatedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    except RoundIndexOutOfRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except PromptModeMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
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
        vocabulary_richness=round_row.vocabulary_richness,
        feedback=evaluation.get("feedback", ""),
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
        session_row, metrics_row = await finalize_linguistic_versatility_session(
            db=db, user=user, session_id=session_id
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de versatilidad no encontrada",
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
        vocabulary_richness_avg=metrics_row.vocabulary_richness_avg,
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
        await abandon_linguistic_versatility_session(
            db=db, user=user, session_id=session_id
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de versatilidad no encontrada",
        )
    except SessionNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )


@router.get(
    "/sessions",
    response_model=list[LinguisticVersatilitySessionListItem],
)
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[LinguisticVersatilitySessionListItem]:
    rows = await list_linguistic_versatility_sessions(db=db, user=user)
    return [
        LinguisticVersatilitySessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            mode=metrics_row.mode,
            rounds_total=metrics_row.rounds_total,
            rounds_completed=metrics_row.rounds_completed,
            vocabulary_richness_avg=metrics_row.vocabulary_richness_avg,
        )
        for session_row, metrics_row in rows
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=LinguisticVersatilitySessionDetail,
)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> LinguisticVersatilitySessionDetail:
    found = await get_linguistic_versatility_session(
        db=db, user=user, session_id=session_id
    )
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de versatilidad no encontrada",
        )
    return _build_detail(*found)
