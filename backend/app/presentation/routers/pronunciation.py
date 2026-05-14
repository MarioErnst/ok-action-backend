from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.pronunciation_metrics import PronunciationMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.ai.pronunciation_gemini import GeminiPronunciationError
from app.infrastructure.audio.mime import verify_audio_mime
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.pronunciation import (
    PhonemeError,
    PhraseEvaluation,
    PronunciationMetricsOutput,
    PronunciationPhraseEvaluationOutput,
    PronunciationPhraseOutput,
    PronunciationSessionCreate,
    PronunciationSessionDetail,
    PronunciationSessionListItem,
    PronunciationWeakestPromptOutput,
)
from app.use_cases.live.sessions import InvalidParentLiveError
from app.use_cases.pronunciation.evaluate_phrase import evaluate_phrase
from app.use_cases.pronunciation.prompts import list_phrases
from app.use_cases.pronunciation.sessions import (
    PronunciationPromptNotAvailableError,
    create_pronunciation_session,
    get_pronunciation_session,
    list_pronunciation_sessions,
    list_session_phrases,
    weakest_prompts,
)

router = APIRouter(prefix="/pronunciation", tags=["pronunciation"])


@router.get("/phrases", response_model=list[PronunciationPhraseOutput])
async def list_phrases_endpoint(
    level: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[PronunciationPhraseOutput]:
    """List pronunciation phrases from the catalog, optionally filtered by level.

    The frontend asks for the active level (basico / intermedio / avanzado)
    via the `level` query param. Without it, returns the full catalog.
    """

    rows = await list_phrases(db, difficulty=level)
    return [PronunciationPhraseOutput.model_validate(r) for r in rows]


def _build_detail(
    session_row: Session, metrics_row: PronunciationMetrics
) -> PronunciationSessionDetail:
    return PronunciationSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=PronunciationMetricsOutput.model_validate(metrics_row),
    )


@router.post("/evaluate", response_model=PhraseEvaluation)
async def evaluate_phrase_endpoint(
    audio: UploadFile,
    phrase_text: str = Form(...),
    phrase_index: int = Form(...),
    level: str = Form(...),
    user: User = Depends(get_current_user),
) -> PhraseEvaluation:
    """Score a single phrase via Gemini.

    The response carries Gemini's per-phrase feedback and phoneme_errors
    for ephemeral display in the UI; none of that is persisted to the DB.
    The frontend aggregates phrase scores and posts /sessions to record
    the session's aggregated metrics.
    """

    mime_type = verify_audio_mime(audio)
    audio_bytes = await audio.read()

    try:
        evaluation = await evaluate_phrase(audio_bytes, mime_type, phrase_text, level)
    except GeminiPronunciationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
        )

    return PhraseEvaluation(
        phrase_text=phrase_text,
        phrase_index=phrase_index,
        overall_score=evaluation["overall_score"],
        vowel_score=evaluation["vowel_score"],
        consonant_score=evaluation["consonant_score"],
        fluency_score=evaluation["fluency_score"],
        intelligibility_score=evaluation["intelligibility_score"],
        feedback=evaluation["feedback"],
        phoneme_errors=[
            PhonemeError(**error_item)
            for error_item in evaluation.get("phoneme_errors", [])
        ],
    )


@router.post(
    "/sessions",
    response_model=PronunciationSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    payload: PronunciationSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> PronunciationSessionDetail:
    try:
        session_row, metrics_row = await create_pronunciation_session(
            db=db, user=user, payload=payload
        )
    except InvalidParentLiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except PronunciationPromptNotAvailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return _build_detail(session_row, metrics_row)


@router.get(
    "/sessions/{session_id}/phrases",
    response_model=list[PronunciationPhraseEvaluationOutput],
)
async def list_session_phrases_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[PronunciationPhraseEvaluationOutput]:
    """Per-phrase breakdown for the given session.

    Returns empty list for sessions persisted before B7. 404 if the session
    does not exist or belongs to a different user.
    """

    rows = await list_session_phrases(db=db, user=user, session_id=session_id)
    if rows is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de pronunciación no encontrada",
        )
    return [PronunciationPhraseEvaluationOutput.model_validate(r) for r in rows]


@router.get(
    "/insights/weakest-prompts",
    response_model=list[PronunciationWeakestPromptOutput],
)
async def weakest_prompts_endpoint(
    limit: int = 5,
    min_practice_count: int = 1,
    level: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[PronunciationWeakestPromptOutput]:
    """Prompts where the user has the lowest historical avg score.

    Drives the "tus frases más difíciles" entry card in the UI. `level`
    (optional) narrows to one difficulty so the UI can show weakest per
    level. Sorted ascending by avg_score.
    """

    if limit <= 0 or limit > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be in (0, 20]",
        )
    rows = await weakest_prompts(
        db=db,
        user=user,
        limit=limit,
        min_practice_count=min_practice_count,
        difficulty=level,
    )
    return [PronunciationWeakestPromptOutput.model_validate(r) for r in rows]


@router.get("/sessions", response_model=list[PronunciationSessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[PronunciationSessionListItem]:
    rows = await list_pronunciation_sessions(db=db, user=user)
    return [
        PronunciationSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            level=metrics_row.level,
            phrases_count=metrics_row.phrases_count,
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=PronunciationSessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> PronunciationSessionDetail:
    found = await get_pronunciation_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de pronunciación no encontrada",
        )
    return _build_detail(*found)
