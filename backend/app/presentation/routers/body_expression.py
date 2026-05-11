from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.body_expression_metrics import BodyExpressionMetrics
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.body_expression import (
    BodyExpressionFeedbackOutput,
    BodyExpressionMetricsOutput,
    BodyExpressionSessionCreate,
    BodyExpressionSessionDetail,
    BodyExpressionSessionListItem,
)
from app.use_cases.body_expression.sessions import (
    create_body_expression_session,
    feedback_from_metrics_row,
    get_body_expression_session,
    list_body_expression_sessions,
)
from app.use_cases.live.sessions import InvalidParentLiveError

router = APIRouter(prefix="/body-expression", tags=["body-expression"])


def _build_detail(
    session_row: Session,
    metrics_row: BodyExpressionMetrics,
    feedback: BodyExpressionFeedbackOutput | None = None,
) -> BodyExpressionSessionDetail:
    return BodyExpressionSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=BodyExpressionMetricsOutput.model_validate(metrics_row),
        feedback=feedback or feedback_from_metrics_row(metrics_row),
    )


@router.post(
    "/sessions",
    response_model=BodyExpressionSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    payload: BodyExpressionSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> BodyExpressionSessionDetail:
    try:
        session_row, metrics_row, feedback = await create_body_expression_session(
            db=db, user=user, payload=payload
        )
    except InvalidParentLiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return _build_detail(session_row, metrics_row, feedback)


@router.get("/sessions", response_model=list[BodyExpressionSessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[BodyExpressionSessionListItem]:
    rows = await list_body_expression_sessions(db=db, user=user)
    return [
        BodyExpressionSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            posture_score=metrics_row.posture_score,
            gesture_score=metrics_row.gesture_score,
            stability_score=metrics_row.stability_score,
            framing_mode=metrics_row.framing_mode,
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=BodyExpressionSessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> BodyExpressionSessionDetail:
    found = await get_body_expression_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesion de expresion corporal no encontrada",
        )
    return _build_detail(*found)
