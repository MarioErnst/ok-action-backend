from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.pause_session import PauseSession
from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.pauses import (
    PauseInterval,
    PauseMetrics,
    PauseSessionListItem,
    PauseSessionRequest,
    PauseSessionResponse,
)
from app.use_cases.pauses.sessions import (
    get_pause_session,
    list_pause_sessions,
    save_pause_session,
)

router = APIRouter(prefix="/pauses", tags=["pauses"])


def _pause_metrics_response(session: PauseSession) -> PauseMetrics:
    return PauseMetrics(
        total_pauses=session.total_pauses,
        total_pause_duration_ms=session.total_pause_duration_ms,
        average_pause_ms=float(session.average_pause_ms),
        longest_pause_ms=session.longest_pause_ms,
        silence_ratio=float(session.silence_ratio),
        classification=session.classification,
        pauses=[PauseInterval(**pause) for pause in session.pauses],
    )


def _pause_session_response(session: PauseSession) -> PauseSessionResponse:
    return PauseSessionResponse(
        id=str(session.id),
        prompt_text=session.prompt_text,
        duration_ms=session.duration_ms,
        pause_metrics=_pause_metrics_response(session),
        created_at=session.created_at.isoformat(),
    )


@router.post("/sessions", response_model=PauseSessionResponse, status_code=201)
async def create_pause_session(
    request: PauseSessionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    pause_session = await save_pause_session(
        data=request.model_dump(),
        user=user,
        session=session,
    )
    return _pause_session_response(pause_session)


@router.get("/sessions", response_model=list[PauseSessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    sessions = await list_pause_sessions(user, session)
    return [
        PauseSessionListItem(
            id=str(item.id),
            prompt_text=item.prompt_text,
            duration_ms=item.duration_ms,
            total_pauses=item.total_pauses,
            silence_ratio=float(item.silence_ratio),
            classification=item.classification,
            created_at=item.created_at.isoformat(),
        )
        for item in sessions
    ]


@router.get("/sessions/{session_id}", response_model=PauseSessionResponse)
async def get_session_detail(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await get_pause_session(session_id, user, session)
    if not result:
        raise HTTPException(status_code=404, detail="Sesion de pausas no encontrada")

    return _pause_session_response(result)
