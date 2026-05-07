# Full module documentation: documentacion/modulos/expresion-facial.md
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.facial_expression import (
    ALLOWED_EMOTIONS,
    EmotionEventResponse,
    SessionCreateRequest,
    SessionDetailResponse,
    SessionListItem,
)
from app.use_cases.facial_expression.sessions import (
    get_facial_expression_session,
    list_facial_expression_sessions,
    save_facial_expression_session,
)

router = APIRouter(prefix="/facial-expression", tags=["facial-expression"])


def _session_to_response(s) -> SessionDetailResponse:
    """Convert a FacialExpressionSession ORM instance to the full response schema."""
    return SessionDetailResponse(
        id=str(s.id),
        duration_ms=s.duration_ms,
        dominant_emotion=s.dominant_emotion,
        dominant_percentage=s.dominant_percentage,
        emotion_distribution=s.emotion_distribution or {},
        created_at=s.created_at.isoformat(),
        events=[
            EmotionEventResponse(
                t_ms=ev.t_ms,
                emotion=ev.emotion,
                gestures=ev.gestures or {},
            )
            for ev in s.events
        ],
    )


@router.post("/sessions", response_model=SessionDetailResponse, status_code=201)
async def create_session(
    request: SessionCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Persist a completed analysis session and return the full saved record."""
    # Reject unknown emotion values at the boundary so the database column
    # stays clean and bugs in the client don't silently corrupt analytics.
    for ev in request.events:
        if ev.emotion not in ALLOWED_EMOTIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Emoción no soportada: {ev.emotion}",
            )

    data = request.model_dump()
    try:
        facial_session = await save_facial_expression_session(data, user, session)
    except Exception:
        await session.rollback()
        raise

    full = await get_facial_expression_session(str(facial_session.id), user, session)
    return _session_to_response(full)


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return a summary list of all facial expression sessions for the user."""
    sessions = await list_facial_expression_sessions(user, session)
    return [
        SessionListItem(
            id=str(s.id),
            duration_ms=s.duration_ms,
            dominant_emotion=s.dominant_emotion,
            dominant_percentage=s.dominant_percentage,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return full detail of a single session including its event timeline."""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    facial_session = await get_facial_expression_session(session_id, user, session)
    if not facial_session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return _session_to_response(facial_session)
