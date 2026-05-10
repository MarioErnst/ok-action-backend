from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Per-phrase Gemini evaluation (ephemeral, never persisted)


class PhraseSpecificError(BaseModel):
    word: str
    expected_stress: str
    actual_issue: str
    suggestion: str


class PhraseEvaluation(BaseModel):
    phrase_text: str
    phrase_index: int
    overall_score: int = Field(ge=0, le=100)
    pronunciation_score: int = Field(ge=0, le=100)
    rhythm_score: int = Field(ge=0, le=100)
    intonation_score: int = Field(ge=0, le=100)
    stress_score: int = Field(ge=0, le=100)
    feedback: str
    specific_errors: list[PhraseSpecificError]


# Persisted session metrics


class AccentuationMetricsInput(BaseModel):
    pronunciation_score: int = Field(ge=0, le=100)
    rhythm_score: int = Field(ge=0, le=100)
    intonation_score: int = Field(ge=0, le=100)
    stress_score: int = Field(ge=0, le=100)
    phrases_count: int = Field(ge=1)


class AccentuationMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pronunciation_score: int
    rhythm_score: int
    intonation_score: int
    stress_score: int
    phrases_count: int


class AccentuationSessionCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    metrics: AccentuationMetricsInput
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "AccentuationSessionCreate":
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be greater than started_at")
        return self


class AccentuationSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: AccentuationMetricsOutput


class AccentuationSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    phrases_count: int
