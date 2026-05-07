# Full module documentation: documentacion/modulos/fonacion.md
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.phonation import (
    PhonationSessionListItem,
    PhonationSessionRequest,
    PhonationSessionResponse,
    ExerciseResultResponse,
)
from app.use_cases.phonation.sessions import (
    get_phonation_session,
    list_phonation_sessions,
    save_phonation_session,
)

router = APIRouter(prefix="/phonation", tags=["phonation"])


def _build_session_response(result) -> PhonationSessionResponse:
    # Centralises entity-to-schema mapping so create_session and
    # get_session_detail do not duplicate the same transformation.
    return PhonationSessionResponse(
        id=str(result.id),
        overall_score=float(result.overall_score),
        avg_hz=float(result.avg_hz),
        observations=result.observations,
        created_at=result.created_at.isoformat(),
        exercises=[
            ExerciseResultResponse(
                id=str(e.id),
                exercise_id=e.exercise_id,
                exercise_type=e.exercise_type,
                avg_hz=float(e.avg_hz),
                stability=float(e.stability),
                breaks=e.breaks,
                in_range=e.in_range,
            )
            for e in result.exercise_results
        ],
    )


@router.post("/sessions", response_model=PhonationSessionResponse, status_code=201)
async def create_session(
    request: PhonationSessionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    phonation_session = await save_phonation_session(
        data=request.model_dump(),
        user=user,
        session=session,
    )

    result = await get_phonation_session(str(phonation_session.id), user, session)

    return _build_session_response(result)


@router.get("/sessions", response_model=list[PhonationSessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    sessions = await list_phonation_sessions(user, session)
    return [
        PhonationSessionListItem(
            id=str(s.id),
            overall_score=float(s.overall_score),
            avg_hz=float(s.avg_hz),
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=PhonationSessionResponse)
async def get_session_detail(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await get_phonation_session(session_id, user, session)
    if not result:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    return _build_session_response(result)
