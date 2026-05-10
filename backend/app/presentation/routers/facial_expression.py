from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.facial_expression_metrics import FacialExpressionMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.facial_expression import (
    FacialExpressionMetricsOutput,
    FacialExpressionSessionCreate,
    FacialExpressionSessionDetail,
    FacialExpressionSessionListItem,
)
from app.use_cases.facial_expression.sessions import (
    create_facial_expression_session,
    get_facial_expression_session,
    list_facial_expression_sessions,
)
from app.use_cases.live.sessions import InvalidParentLiveError

router = APIRouter(prefix="/facial-expression", tags=["facial-expression"])


def _build_detail(
    session_row: Session, metrics_row: FacialExpressionMetrics
) -> FacialExpressionSessionDetail:
    return FacialExpressionSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=FacialExpressionMetricsOutput.model_validate(metrics_row),
    )


@router.post(
    "/sessions",
    response_model=FacialExpressionSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    payload: FacialExpressionSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> FacialExpressionSessionDetail:
    try:
        session_row, metrics_row = await create_facial_expression_session(
            db=db, user=user, payload=payload
        )
    except InvalidParentLiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return _build_detail(session_row, metrics_row)


@router.get("/sessions", response_model=list[FacialExpressionSessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[FacialExpressionSessionListItem]:
    rows = await list_facial_expression_sessions(db=db, user=user)
    return [
        FacialExpressionSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            top_emotion=metrics_row.top_emotion,
            expressiveness_score=metrics_row.expressiveness_score,
        )
        for session_row, metrics_row in rows
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=FacialExpressionSessionDetail,
)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> FacialExpressionSessionDetail:
    found = await get_facial_expression_session(
        db=db, user=user, session_id=session_id
    )
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de expresión facial no encontrada",
        )
    return _build_detail(*found)
