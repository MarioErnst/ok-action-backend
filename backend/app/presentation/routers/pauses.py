from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.pause_metrics import PauseMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.pauses import (
    PauseMetricsOutput,
    PauseSessionCreate,
    PauseSessionDetail,
    PauseSessionListItem,
)
from app.use_cases.live.sessions import InvalidParentLiveError
from app.use_cases.pauses.sessions import (
    create_pause_session,
    get_pause_session,
    list_pause_sessions,
)

router = APIRouter(prefix="/pauses", tags=["pauses"])


def _build_detail(
    session_row: Session, metrics_row: PauseMetrics
) -> PauseSessionDetail:
    return PauseSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=PauseMetricsOutput.model_validate(metrics_row),
    )


@router.post(
    "/sessions",
    response_model=PauseSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    payload: PauseSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> PauseSessionDetail:
    try:
        session_row, metrics_row = await create_pause_session(
            db=db, user=user, payload=payload
        )
    except InvalidParentLiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return _build_detail(session_row, metrics_row)


@router.get("/sessions", response_model=list[PauseSessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[PauseSessionListItem]:
    rows = await list_pause_sessions(db=db, user=user)
    return [
        PauseSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            pauses_count=metrics_row.pauses_count,
            silence_pct=metrics_row.silence_pct,
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=PauseSessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> PauseSessionDetail:
    found = await get_pause_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de pausas no encontrada",
        )
    return _build_detail(*found)
