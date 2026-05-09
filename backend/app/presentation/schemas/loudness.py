from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Presets


class LoudnessPresetCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    description: str | None = None
    silence_offset_db: float
    low_offset_db: float
    optimal_offset_db: float
    clip_threshold_db: float


class LoudnessPresetUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    silence_offset_db: float | None = None
    low_offset_db: float | None = None
    optimal_offset_db: float | None = None
    clip_threshold_db: float | None = None


class LoudnessPresetOutput(BaseModel):
    id: UUID
    label: str
    description: str | None
    silence_offset_db: float
    low_offset_db: float
    optimal_offset_db: float
    clip_threshold_db: float
    is_default: bool
    is_global: bool


# Sessions


class LoudnessMetricsInput(BaseModel):
    preset_id: UUID
    optimal_pct: int = Field(ge=0, le=100)
    low_pct: int = Field(ge=0, le=100)
    high_pct: int = Field(ge=0, le=100)
    clipping_pct: int = Field(ge=0, le=100)
    peak_db: float

    @model_validator(mode="after")
    def validate_bands_sum(self) -> "LoudnessMetricsInput":
        total = self.optimal_pct + self.low_pct + self.high_pct + self.clipping_pct
        if total != 100:
            raise ValueError(
                f"loudness band percentages must sum to 100, got {total}"
            )
        return self


class LoudnessMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    preset_id: UUID
    optimal_pct: int
    low_pct: int
    high_pct: int
    clipping_pct: int
    peak_db: float


class LoudnessSessionCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    metrics: LoudnessMetricsInput

    @model_validator(mode="after")
    def validate_time_range(self) -> "LoudnessSessionCreate":
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be greater than started_at")
        return self


class LoudnessSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: LoudnessMetricsOutput


class LoudnessSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    optimal_pct: int
    preset_id: UUID
