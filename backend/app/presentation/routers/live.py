from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import StopReasonEnum
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.live import (
    AbandonSessionRequest,
    FinalizeSessionResponse,
    LiveChildOutput,
    LiveMetricsOutput,
    LiveSessionDetail,
    LiveSessionListItem,
    StartSessionResponse,
)
from app.use_cases.live.sessions import (
    SessionNotActiveError,
    SessionNotFoundError,
    abandon_live_session,
    finalize_live_session,
    get_live_session,
    list_live_sessions,
    start_live_session,
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
