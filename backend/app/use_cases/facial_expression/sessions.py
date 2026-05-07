# Business logic for facial expression session CRUD: documentacion/modulos/expresion-facial.md
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.facial_expression_session import FacialExpressionSession
from app.domain.entities.facial_expression_question_result import (
    FacialExpressionQuestionResult,
)
from app.domain.entities.user import User
from app.use_cases.facial_expression.analyze_session import calculate_session_scores


async def save_facial_expression_session(
    data: dict,
    user: User,
    session: AsyncSession,
) -> FacialExpressionSession:
    """Compute scores from raw frame data, persist session and question results.

    Args:
        data: dict with keys "baseline" and "questions".
              baseline: {"pucker": float, "brow_down": float, "lips_down": float}
              questions: list of {"question_id": str, "question_text": str,
                                  "duration_ms": int,
                                  "frames": [{"t": int, "pk": float, "bd": float, "ld": float}]}
        user: authenticated User entity.
        session: async database session.

    Returns:
        Persisted FacialExpressionSession instance.
    """
    baseline = data["baseline"]
    questions = data["questions"]

    scores = calculate_session_scores(baseline, questions)

    facial_session = FacialExpressionSession(
        user_id=user.id,
        baseline_pucker=baseline["pucker"],
        baseline_brow_down=baseline["brow_down"],
        baseline_lips_down=baseline["lips_down"],
        overall_score=scores["overall_score"],
    )
    session.add(facial_session)
    await session.flush()

    # Build a lookup by question_id so each question row gets its computed scores.
    score_map = {r["question_id"]: r for r in scores["question_results"]}

    for q in questions:
        s = score_map.get(q["question_id"], {})
        result = FacialExpressionQuestionResult(
            session_id=facial_session.id,
            question_id=q["question_id"],
            question_text=q["question_text"],
            duration_ms=q["duration_ms"],
            frames=q["frames"],
            pucker_score=s.get("pucker_score"),
            brow_down_score=s.get("brow_down_score"),
            lips_down_score=s.get("lips_down_score"),
            question_score=s.get("question_score"),
        )
        session.add(result)

    await session.commit()
    await session.refresh(facial_session)
    return facial_session


async def list_facial_expression_sessions(
    user: User,
    session: AsyncSession,
) -> list[FacialExpressionSession]:
    """Return all facial expression sessions for a user, newest first.

    Args:
        user: authenticated User entity.
        session: async database session.

    Returns:
        List of FacialExpressionSession instances ordered by created_at descending.
    """
    result = await session.execute(
        select(FacialExpressionSession)
        .where(FacialExpressionSession.user_id == user.id)
        .order_by(FacialExpressionSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_facial_expression_session(
    session_id: str,
    user: User,
    session: AsyncSession,
) -> FacialExpressionSession | None:
    """Return a single session with its question results, or None if not found or not owned.

    Args:
        session_id: UUID string of the session to retrieve.
        user: authenticated User entity used to enforce ownership.
        session: async database session.

    Returns:
        FacialExpressionSession with question_results eagerly loaded, or None.
    """
    result = await session.execute(
        select(FacialExpressionSession)
        .options(selectinload(FacialExpressionSession.question_results))
        .where(
            FacialExpressionSession.id == session_id,
            FacialExpressionSession.user_id == user.id,
        )
    )
    return result.scalar_one_or_none()
