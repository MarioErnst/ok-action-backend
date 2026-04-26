from pydantic import BaseModel, Field


class PauseInterval(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class PauseMetrics(BaseModel):
    total_pauses: int = Field(ge=0)
    total_pause_duration_ms: int = Field(ge=0)
    average_pause_ms: float = Field(ge=0)
    longest_pause_ms: int = Field(ge=0)
    silence_ratio: float = Field(ge=0, le=1)
    classification: str
    pauses: list[PauseInterval]


class PauseSessionRequest(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=500)
    duration_ms: int = Field(gt=0)
    pause_metrics: PauseMetrics


class PauseSessionResponse(BaseModel):
    id: str
    prompt_text: str
    duration_ms: int
    pause_metrics: PauseMetrics
    created_at: str


class PauseSessionListItem(BaseModel):
    id: str
    prompt_text: str
    duration_ms: int
    total_pauses: int
    silence_ratio: float
    classification: str
    created_at: str
