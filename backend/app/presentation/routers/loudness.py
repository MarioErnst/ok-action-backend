from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import get_current_user
from app.presentation.schemas.loudness import (
    LoudnessPresetCreateRequest,
    LoudnessPresetResponse,
    LoudnessPresetUpdateRequest,
    LoudnessSessionListItem,
    LoudnessSessionRequest,
    LoudnessSessionResponse,
)
from app.use_cases.loudness.presets import (
    create_preset,
    delete_preset,
    list_presets,
    update_preset,
)
from app.use_cases.loudness.sessions import (
    list_loudness_sessions,
    save_loudness_session,
)

router = APIRouter(prefix="/loudness", tags=["loudness"])


def _preset_to_response(preset) -> LoudnessPresetResponse:
    return LoudnessPresetResponse(
        id=str(preset.id),
        label=preset.label,
        description=preset.description,
        silence_offset_db=float(preset.silence_offset_db),
        too_low_offset_db=float(preset.too_low_offset_db),
        optimal_offset_db=float(preset.optimal_offset_db),
        clip_threshold_dbfs=float(preset.clip_threshold_dbfs),
        is_default=preset.is_default,
    )


@router.get("/presets", response_model=list[LoudnessPresetResponse])
async def get_presets(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    presets = await list_presets(user, session)
    return [_preset_to_response(p) for p in presets]


@router.post("/presets", response_model=LoudnessPresetResponse, status_code=201)
async def create_preset_endpoint(
    request: LoudnessPresetCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    preset = await create_preset(request.model_dump(), user, session)
    return _preset_to_response(preset)


@router.put("/presets/{preset_id}", response_model=LoudnessPresetResponse)
async def update_preset_endpoint(
    preset_id: str,
    request: LoudnessPresetUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    preset = await update_preset(preset_id, request.model_dump(exclude_unset=True), user, session)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset no encontrado o no es tuyo")
    return _preset_to_response(preset)


@router.delete("/presets/{preset_id}", status_code=204)
async def delete_preset_endpoint(
    preset_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    deleted = await delete_preset(preset_id, user, session)
    if not deleted:
        raise HTTPException(status_code=404, detail="Preset no encontrado o no es tuyo")


@router.post("/sessions", response_model=LoudnessSessionResponse, status_code=201)
async def create_loudness_session(
    request: LoudnessSessionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    loudness_session = await save_loudness_session(request.model_dump(), user, session)
    return LoudnessSessionResponse(
        id=str(loudness_session.id),
        preset_id=str(loudness_session.preset_id),
        duration_ms=loudness_session.duration_ms,
        optimal_percent=float(loudness_session.optimal_percent),
        peak_db=float(loudness_session.peak_db),
        band_time_ms=loudness_session.band_time_ms,
        created_at=loudness_session.created_at.isoformat(),
    )


@router.get("/sessions", response_model=list[LoudnessSessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    sessions = await list_loudness_sessions(user, session)
    return [
        LoudnessSessionListItem(
            id=str(s.id),
            preset_id=str(s.preset_id),
            optimal_percent=float(s.optimal_percent),
            duration_ms=s.duration_ms,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]
