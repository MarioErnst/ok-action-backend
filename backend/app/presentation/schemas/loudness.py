from pydantic import BaseModel


class LoudnessPresetResponse(BaseModel):
    id: str
    label: str
    description: str | None
    silence_offset_db: float
    too_low_offset_db: float
    optimal_offset_db: float
    clip_threshold_dbfs: float
    is_default: bool


class LoudnessPresetCreateRequest(BaseModel):
    label: str
    description: str | None = None
    silence_offset_db: float
    too_low_offset_db: float
    optimal_offset_db: float
    clip_threshold_dbfs: float


class LoudnessPresetUpdateRequest(BaseModel):
    label: str | None = None
    description: str | None = None
    silence_offset_db: float | None = None
    too_low_offset_db: float | None = None
    optimal_offset_db: float | None = None
    clip_threshold_dbfs: float | None = None


class LoudnessSessionRequest(BaseModel):
    preset_id: str
    duration_ms: int
    optimal_percent: float
    peak_db: float
    band_time_ms: dict[str, int]


class LoudnessSessionResponse(BaseModel):
    id: str
    preset_id: str
    duration_ms: int
    optimal_percent: float
    peak_db: float
    band_time_ms: dict[str, int]
    created_at: str


class LoudnessSessionListItem(BaseModel):
    id: str
    preset_id: str
    optimal_percent: float
    duration_ms: int
    created_at: str
