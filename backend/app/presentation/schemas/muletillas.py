from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Per-response Gemini evaluation (ephemeral, never persisted)


class MuletillaDetectedEphemeral(BaseModel):
    """Single muletilla detected by Gemini in a response. Carries Gemini's
    suggestion text; that suggestion is shown in the UI but not persisted."""

    word: str
    count: int = Field(ge=1)
    severity: Literal["low", "medium", "high"]
    suggestion: str


class MuletillasEvaluationResponse(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    fluency_score: int = Field(ge=0, le=100)
    muletillas_score: int = Field(ge=0, le=100)
    total_muletillas_count: int = Field(ge=0)
    muletillas_per_minute: float = Field(ge=0)
    muletillas_detected: list[MuletillaDetectedEphemeral]
    feedback: str
    strengths: str
    improvement_areas: str


class RandomQuestionResponse(BaseModel):
    question: str


# Persisted session metrics


class MuletillaWordInput(BaseModel):
    """Per-word usage submitted by the client. word will be normalized
    server-side (lowercased, trimmed, accents stripped) before insert."""

    word: str = Field(min_length=1, max_length=100)
    count: int = Field(ge=1)
    severity: Literal["low", "medium", "high"]


class MuletillasMetricsInput(BaseModel):
    fluency_score: int = Field(ge=0, le=100)
    words: list[MuletillaWordInput] = Field(default_factory=list)


class MuletillaWordOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    word: str
    count: int
    severity: Literal["low", "medium", "high"]


class MuletillasMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fluency_score: int
    muletillas_count: int


class MuletillasSessionCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    metrics: MuletillasMetricsInput
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "MuletillasSessionCreate":
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be greater than started_at")
        return self


class MuletillasSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: MuletillasMetricsOutput
    words: list[MuletillaWordOutput]


class MuletillasSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    muletillas_count: int
    fluency_score: int
