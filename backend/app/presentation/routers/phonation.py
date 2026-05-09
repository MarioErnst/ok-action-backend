from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.phonation_metrics import PhonationMetrics
from app.domain.entities.phonation_session_exercise import PhonationSessionExercise
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.phonation import (
    PhonationExerciseOutput,
    PhonationMetricsOutput,
    PhonationSessionCreate,
    PhonationSessionDetail,
    PhonationSessionListItem,
)
from app.use_cases.phonation.sessions import (
    create_phonation_session,
    get_phonation_session,
    list_phonation_sessions,
)

router = APIRouter(prefix="/phonation", tags=["phonation"])


def _build_detail(
    session_row: Session,
    metrics_row: PhonationMetrics,
    exercise_rows: list[PhonationSessionExercise],
) -> PhonationSessionDetail:
    return PhonationSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=PhonationMetricsOutput.model_validate(metrics_row),
        exercises=[
            PhonationExerciseOutput.model_validate(exercise)
            for exercise in exercise_rows
        ],
    )


@router.post(
    "/sessions",
    response_model=PhonationSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: PhonationSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> PhonationSessionDetail:
    session_row, metrics_row, exercise_rows = await create_phonation_session(
        db=db, user=user, payload=payload
    )
    return _build_detail(session_row, metrics_row, exercise_rows)


@router.get("/sessions", response_model=list[PhonationSessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[PhonationSessionListItem]:
    rows = await list_phonation_sessions(db=db, user=user)
    return [
        PhonationSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            avg_hz=float(metrics_row.avg_hz),
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=PhonationSessionDetail)
async def get_session_detail(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> PhonationSessionDetail:
    found = await get_phonation_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de fonación no encontrada",
        )
    return _build_detail(*found)
