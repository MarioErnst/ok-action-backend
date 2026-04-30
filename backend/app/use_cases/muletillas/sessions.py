from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.muletillas_session import MuletillasSession, PhraseMuletillas
from app.domain.entities.user import User


async def save_muletillas_session(
    data: dict,
    user: User,
    session: AsyncSession,
) -> MuletillasSession:
    """Persiste una sesion de muletillas y sus muletillas detectadas."""
    muletillas_session = MuletillasSession(
        user_id=user.id,
        question_text=data["question_text"],
        overall_score=data["overall_score"],
        fluency_score=data["fluency_score"],
        muletillas_score=data["muletillas_score"],
        total_muletillas_count=data["total_muletillas_count"],
        muletillas_per_minute=data["muletillas_per_minute"],
        feedback=data["feedback"],
        strengths=data["strengths"],
        improvement_areas=data["improvement_areas"],
    )
    session.add(muletillas_session)
    await session.flush()
    await session.refresh(muletillas_session)

    for detected in data.get("muletillas_detected", []):
        session.add(PhraseMuletillas(
            session_id=muletillas_session.id,
            word=detected["word"],
            count=detected["count"],
            severity=detected["severity"],
            suggestion=detected["suggestion"],
        ))

    await session.commit()
    await session.refresh(muletillas_session)
    return muletillas_session


async def list_muletillas_sessions(
    user: User,
    session: AsyncSession,
) -> list[MuletillasSession]:
    """Lista todas las sesiones del usuario ordenadas por fecha descendente."""
    result = await session.execute(
        select(MuletillasSession)
        .where(MuletillasSession.user_id == user.id)
        .order_by(MuletillasSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_muletillas_session(
    session_id: str,
    user: User,
    session: AsyncSession,
) -> MuletillasSession | None:
    """Obtiene una sesion con sus muletillas detectadas cargadas."""
    result = await session.execute(
        select(MuletillasSession)
        .options(selectinload(MuletillasSession.muletillas_detected))
        .where(
            MuletillasSession.id == session_id,
            MuletillasSession.user_id == user.id,
        )
    )
    return result.scalar_one_or_none()
