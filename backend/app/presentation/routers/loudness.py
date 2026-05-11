from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.loudness_metrics import LoudnessMetrics
from app.domain.entities.loudness_preset import LoudnessPreset
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.loudness import (
    LoudnessMetricsOutput,
    LoudnessPresetCreate,
    LoudnessPresetOutput,
    LoudnessPresetUpdate,
    LoudnessSessionCreate,
    LoudnessSessionDetail,
    LoudnessSessionListItem,
)
from app.use_cases.loudness.presets import (
    PresetReferencedError,
    create_preset,
    delete_preset,
    list_presets,
    update_preset,
)
from app.use_cases.live.sessions import InvalidParentLiveError
from app.use_cases.loudness.sessions import (
    PresetNotAvailableError,
    create_loudness_session,
    get_loudness_session,
    list_loudness_sessions,
)

router = APIRouter(prefix="/loudness", tags=["loudness"])


def _preset_to_output(preset: LoudnessPreset) -> LoudnessPresetOutput:
    return LoudnessPresetOutput(
        id=preset.id,
        label=preset.label,
        description=preset.description,
        silence_offset_db=float(preset.silence_offset_db),
        low_offset_db=float(preset.low_offset_db),
        optimal_offset_db=float(preset.optimal_offset_db),
        clip_threshold_db=float(preset.clip_threshold_db),
        is_default=preset.is_default,
        is_global=preset.user_id is None,
    )


def _build_session_detail(
    session_row: Session, metrics_row: LoudnessMetrics
) -> LoudnessSessionDetail:
    return LoudnessSessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=LoudnessMetricsOutput.model_validate(metrics_row),
    )


# Presets


@router.get("/presets", response_model=list[LoudnessPresetOutput])
async def list_presets_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[LoudnessPresetOutput]:
    presets = await list_presets(db=db, user=user)
    return [_preset_to_output(p) for p in presets]


@router.post(
    "/presets",
    response_model=LoudnessPresetOutput,
    status_code=status.HTTP_201_CREATED,
)
async def create_preset_endpoint(
    payload: LoudnessPresetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> LoudnessPresetOutput:
    preset = await create_preset(db=db, user=user, payload=payload)
    return _preset_to_output(preset)


@router.put("/presets/{preset_id}", response_model=LoudnessPresetOutput)
async def update_preset_endpoint(
    preset_id: UUID,
    payload: LoudnessPresetUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> LoudnessPresetOutput:
    preset = await update_preset(
        db=db, user=user, preset_id=preset_id, payload=payload
    )
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset no encontrado o no editable",
        )
    return _preset_to_output(preset)


@router.delete(
    "/presets/{preset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_preset_endpoint(
    preset_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    try:
        deleted = await delete_preset(db=db, user=user, preset_id=preset_id)
    except PresetReferencedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este preset está siendo usado por sesiones existentes y no se puede eliminar",
        )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset no encontrado o no eliminable",
        )


# Sessions


@router.post(
    "/sessions",
    response_model=LoudnessSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    payload: LoudnessSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> LoudnessSessionDetail:
    try:
        session_row, metrics_row = await create_loudness_session(
            db=db, user=user, payload=payload
        )
    except (PresetNotAvailableError, InvalidParentLiveError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return _build_session_detail(session_row, metrics_row)


@router.get("/sessions", response_model=list[LoudnessSessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[LoudnessSessionListItem]:
    rows = await list_loudness_sessions(db=db, user=user)
    return [
        LoudnessSessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            optimal_pct=metrics_row.optimal_pct,
            preset_id=metrics_row.preset_id,
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=LoudnessSessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> LoudnessSessionDetail:
    found = await get_loudness_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de volumen no encontrada",
        )
    return _build_session_detail(*found)
