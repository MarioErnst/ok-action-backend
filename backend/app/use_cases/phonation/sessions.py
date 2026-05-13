from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ExerciseTypeEnum, ModuleEnum, SessionStatusEnum
from app.domain.entities.phonation_metrics import PhonationMetrics
from app.domain.entities.phonation_session_exercise import PhonationSessionExercise
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.presentation.schemas.phonation import PhonationSessionCreate
from app.use_cases.live.sessions import validate_parent_live_session


async def create_phonation_session(
    db: AsyncSession,
    user: User,
    payload: PhonationSessionCreate,
) -> tuple[Session, PhonationMetrics, list[PhonationSessionExercise]]:
    """Persist a completed phonation session as one transaction.

    Inserts the root sessions row, the 1:1 phonation_metrics row, and one
    phonation_session_exercises row per exercise. Server derives duration_ms
    from started_at/ended_at to avoid trusting client-side derived values.
    """

    if payload.parent_id is not None:
        await validate_parent_live_session(db, user, payload.parent_id)

    duration_ms = int((payload.ended_at - payload.started_at).total_seconds() * 1000)

    session_row = Session(
        user_id=user.id,
        module=ModuleEnum.phonation,
        parent_id=payload.parent_id,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_ms=duration_ms,
        score=payload.score,
        status=SessionStatusEnum.completed,
    )
    db.add(session_row)
    await db.flush()

    metrics_row = PhonationMetrics(
        session_id=session_row.id,
        avg_hz=payload.metrics.avg_hz,
        stability_score=payload.metrics.stability_score,
        breaks_count=payload.metrics.breaks_count,
        exercises_count=payload.metrics.exercises_count,
    )
    db.add(metrics_row)

    exercise_rows = [
        PhonationSessionExercise(
            session_id=session_row.id,
            exercise_type=ExerciseTypeEnum(exercise.exercise_type),
            avg_hz=exercise.avg_hz,
            stability_score=exercise.stability_score,
            breaks_count=exercise.breaks_count,
            in_range_pct=exercise.in_range_pct,
            max_sustained_voicing_ms=exercise.max_sustained_voicing_ms,
            db_slope=exercise.db_slope,
            weak_phrase_endings_count=exercise.weak_phrase_endings_count,
        )
        for exercise in payload.exercises
    ]
    db.add_all(exercise_rows)

    await db.commit()
    await db.refresh(session_row)
    await db.refresh(metrics_row)

    # Sort by enum definition order so this matches the order Postgres uses
    # natively for the get endpoint (Postgres orders ENUM columns by the
    # position in the type definition, not alphabetically).
    enum_order = {member: index for index, member in enumerate(ExerciseTypeEnum)}
    exercise_rows.sort(key=lambda row: enum_order[row.exercise_type])
    return session_row, metrics_row, exercise_rows


async def list_phonation_sessions(
    db: AsyncSession,
    user: User,
) -> list[tuple[Session, PhonationMetrics]]:
    """Timeline of completed standalone phonation sessions for a user.

    parent_id IS NULL filters out phonation sessions that belong to a live
    composition; those should be exposed through the live module's history.
    """

    query = (
        select(Session, PhonationMetrics)
        .join(PhonationMetrics, PhonationMetrics.session_id == Session.id)
        .where(
            Session.user_id == user.id,
            Session.module == ModuleEnum.phonation,
            Session.parent_id.is_(None),
        )
        .order_by(Session.started_at.desc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_phonation_session(
    db: AsyncSession,
    user: User,
    session_id: UUID,
) -> tuple[Session, PhonationMetrics, list[PhonationSessionExercise]] | None:
    """Detail of one phonation session owned by the given user.

    Returns None when the session does not exist or belongs to another user;
    the router maps that to HTTP 404 to avoid leaking ownership information.
    """

    session_query = select(Session).where(
        Session.id == session_id,
        Session.module == ModuleEnum.phonation,
    )
    session_result = await db.execute(session_query)
    session_row = session_result.scalar_one_or_none()

    if session_row is None or session_row.user_id != user.id:
        return None

    metrics_result = await db.execute(
        select(PhonationMetrics).where(PhonationMetrics.session_id == session_id)
    )
    metrics_row = metrics_result.scalar_one_or_none()
    if metrics_row is None:
        return None

    exercises_result = await db.execute(
        select(PhonationSessionExercise)
        .where(PhonationSessionExercise.session_id == session_id)
        .order_by(PhonationSessionExercise.exercise_type)
    )
    exercise_rows = list(exercises_result.scalars().all())

    return session_row, metrics_row, exercise_rows
