from fastapi import APIRouter, Depends, Query
from typing import List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.domain.entities.user import User
from app.domain.entities.session import Session
from app.domain.entities.enums import ModuleEnum
from app.presentation.schemas.profile import TimeRange, TimelineResponse
from app.use_cases.profile.timeline import get_user_timeline

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/timeline", response_model=TimelineResponse)
async def get_profile_timeline(
    range: TimeRange = Query(default="30d", description="Window length: 7d, 30d, 90d or all."),
    module: str = Query(
        default="all",
        description="ModuleEnum value to filter (e.g. 'phonation') or 'all' to aggregate every module.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    """Return per-day aggregates of the user's sessions for the dashboard charts."""
    return await get_user_timeline(db, current_user.id, range_=range, module=module)

@router.get("/history", response_model=List[Any])
async def get_user_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Devuelve el historial consolidado de ejercicios.
    """
    # Get average score and count per module for the current user
    stmt = (
        select(
            Session.module,
            func.avg(Session.score).label("avg_score"),
            func.count(Session.id).label("session_count")
        )
        .where(Session.user_id == current_user.id)
        .where(Session.score.is_not(None))
        .group_by(Session.module)
    )
    result = await db.execute(stmt)
    rows = result.all()

    module_stats = {}
    for row in rows:
        mod_val = row.module.value if hasattr(row.module, "value") else str(row.module)
        module_stats[mod_val] = {
            "avg_score": int(row.avg_score) if row.avg_score is not None else 0,
            "has_sessions": row.session_count > 0
        }

    # Also check if there are ANY sessions per module (even without score) to mark as viewed
    stmt_any = (
        select(Session.module, func.count(Session.id))
        .where(Session.user_id == current_user.id)
        .group_by(Session.module)
    )
    result_any = await db.execute(stmt_any)
    for row in result_any.all():
        mod_val = row.module.value if hasattr(row.module, "value") else str(row.module)
        if mod_val not in module_stats:
            module_stats[mod_val] = {"avg_score": 0, "has_sessions": True}
        else:
            module_stats[mod_val]["has_sessions"] = True

    # -- MOCK TEMPORAL PARA PRUEBAS (Se activa solo si la BD está vacía para este usuario) --
    if not module_stats:
        module_stats = {
            ModuleEnum.phonation.value: {"avg_score": 88, "has_sessions": True},
            ModuleEnum.pauses.value: {"avg_score": 92, "has_sessions": True}
        }
    # ---------------------------------------------------------------------------------

    history = [
        {
            "moduleId": "1",
            "moduleName": "Fonación",
            "iconName": "phonation",
            "averageScore": module_stats.get(ModuleEnum.phonation.value, {}).get("avg_score", 0),
            "categories": [
                {
                    "id": "cat-sustained",
                    "title": "Vocales sostenidas",
                    "exercises": [
                        {
                            "id": "sustained-a",
                            "title": "Sostén la vocal A",
                            "tags": ["5s", "100-200 Hz"],
                            "viewed": module_stats.get(ModuleEnum.phonation.value, {}).get("has_sessions", False)
                        },
                        {
                            "id": "sustained-e",
                            "title": "Sostén la vocal E",
                            "tags": ["5s", "100-200 Hz"],
                            "viewed": module_stats.get(ModuleEnum.phonation.value, {}).get("has_sessions", False)
                        }
                    ]
                }
            ]
        },
        {
            "moduleId": "2",
            "moduleName": "Pronunciación",
            "iconName": "pronunciation",
            "averageScore": module_stats.get(ModuleEnum.pronunciation.value, {}).get("avg_score", 0),
            "categories": [
                {
                    "id": "cat-basico",
                    "title": "Nivel Básico",
                    "exercises": [
                        {
                            "id": "pron-basico-1",
                            "title": "Frase de ejemplo básica",
                            "tags": ["Básico"],
                            "viewed": module_stats.get(ModuleEnum.pronunciation.value, {}).get("has_sessions", False)
                        }
                    ]
                }
            ]
        },
        {
            "moduleId": "3",
            "moduleName": "Pausas",
            "iconName": "pauses",
            "averageScore": module_stats.get(ModuleEnum.pauses.value, {}).get("avg_score", 0),
            "categories": [
                {
                    "id": "cat-pauses",
                    "title": "Control de respiración",
                    "exercises": [
                        {
                            "id": "pauses-1",
                            "title": "Pausas discursivas",
                            "tags": ["Intermedio"],
                            "viewed": module_stats.get(ModuleEnum.pauses.value, {}).get("has_sessions", False)
                        },
                        {
                            "id": "pauses-2",
                            "title": "Pausas dramáticas",
                            "tags": ["Avanzado"],
                            "viewed": module_stats.get(ModuleEnum.pauses.value, {}).get("has_sessions", False)
                        }
                    ]
                }
            ]
        },
        {
            "moduleId": "4",
            "moduleName": "Fluidez",
            "iconName": "fluency",
            "averageScore": module_stats.get(ModuleEnum.fluency.value, {}).get("avg_score", 0),
            "categories": [
                {
                    "id": "cat-fluency",
                    "title": "Ritmo y constancia",
                    "exercises": [
                        {
                            "id": "fluency-1",
                            "title": "Lectura ágil",
                            "tags": ["1 min"],
                            "viewed": module_stats.get(ModuleEnum.fluency.value, {}).get("has_sessions", False)
                        }
                    ]
                }
            ]
        },
        {
            "moduleId": "5",
            "moduleName": "Consistencia",
            "iconName": "consistency",
            "averageScore": module_stats.get(ModuleEnum.consistency.value, {}).get("avg_score", 0),
            "categories": [
                {
                    "id": "cat-consistency",
                    "title": "Manejo del tema",
                    "exercises": [
                        {
                            "id": "cons-1",
                            "title": "Discurso improvisado",
                            "tags": ["Experto"],
                            "viewed": module_stats.get(ModuleEnum.consistency.value, {}).get("has_sessions", False)
                        }
                    ]
                }
            ]
        }
    ]
    return history
