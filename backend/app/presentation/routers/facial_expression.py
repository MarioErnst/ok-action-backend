# Full module documentation: documentacion/modulos/expresion_facial.md
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.facial_expression import (
    FacialExpressionSessionListItem,
    FacialExpressionSessionRequest,
    FacialExpressionSessionResponse,
    QuestionResultResponse,
)
from app.use_cases.facial_expression.sessions import (
    get_facial_expression_session,
    list_facial_expression_sessions,
    save_facial_expression_session,
)

router = APIRouter(prefix="/facial-expression", tags=["facial-expression"])


def _session_to_response(s) -> FacialExpressionSessionResponse:
    """Convert a FacialExpressionSession ORM instance to the full response schema.

    Score fields are passed through verbatim (including None) so callers can
    distinguish missing scores from a worst-case score of zero.
    """
    return FacialExpressionSessionResponse(
        id=str(s.id),
        overall_score=s.overall_score,
        question_results=[
            QuestionResultResponse(
                question_id=qr.question_id,
                question_text=qr.question_text,
                duration_ms=qr.duration_ms,
                pucker_score=qr.pucker_score,
                brow_down_score=qr.brow_down_score,
                lips_down_score=qr.lips_down_score,
                question_score=qr.question_score,
            )
            for qr in s.question_results
        ],
        created_at=s.created_at.isoformat(),
    )


@router.post("/sessions", response_model=FacialExpressionSessionResponse, status_code=201)
async def create_session(
    request: FacialExpressionSessionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Save a facial expression session, compute scores, and return the full result."""
    data = request.model_dump()
    try:
        facial_session = await save_facial_expression_session(data, user, session)
    except Exception:
        # Roll back any partial inserts so the connection is returned in a clean state.
        await session.rollback()
        raise
    full = await get_facial_expression_session(str(facial_session.id), user, session)
    return _session_to_response(full)


@router.get("/sessions", response_model=list[FacialExpressionSessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return a summary list of all facial expression sessions for the authenticated user."""
    sessions = await list_facial_expression_sessions(user, session)
    return [
        FacialExpressionSessionListItem(
            id=str(s.id),
            overall_score=s.overall_score,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=FacialExpressionSessionResponse)
async def get_session_detail(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return the full details of a single facial expression session including per-question scores."""
    # Reject malformed UUIDs with 404 instead of letting the DB driver raise.
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    facial_session = await get_facial_expression_session(session_id, user, session)
    if not facial_session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return _session_to_response(facial_session)
