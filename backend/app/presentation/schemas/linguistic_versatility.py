from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Catalog


class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str
    category: str
    difficulty: str


# Session lifecycle


class StartSessionRequest(BaseModel):
    mode: Literal["guided", "free"]
    rounds_total: int = Field(ge=1, le=20)


class StartSessionResponse(BaseModel):
    session_id: UUID
    started_at: datetime
    mode: Literal["guided", "free"]
    rounds_total: int
    prompts: list[PromptOut]


class EvaluateRoundRequestForm(BaseModel):
    """Documentation-only mirror of the multipart Form fields. FastAPI does
    not support nested Pydantic models for multipart, so the router declares
    each field with Form(...) directly. prompt_id is required in guided mode
    and must be omitted in free mode; the router validates that pairing."""

    round_index: int = Field(ge=0)
    prompt_id: UUID | None = None


class EvaluateRoundResponse(BaseModel):
    """Per-round evaluation result. Carries Gemini's feedback for ephemeral
    display in the UI; only scores and is_audio_intelligible are persisted."""

    round_index: int
    prompt_id: UUID | None
    is_audio_intelligible: bool
    score: int | None = Field(default=None, ge=0, le=100)
    vocabulary_richness: int | None = Field(default=None, ge=0, le=100)
    feedback: str


class FinalizeSessionResponse(BaseModel):
    session_id: UUID
    status: Literal["completed", "aborted"]
    score: int | None
    rounds_completed: int
    rounds_total: int
    vocabulary_richness_avg: int | None


# Persisted detail


class LinguisticVersatilityRoundOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    round_index: int
    prompt_id: UUID | None
    score: int | None
    vocabulary_richness: int | None
    is_audio_intelligible: bool


class LinguisticVersatilityMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mode: Literal["guided", "free"]
    rounds_total: int
    rounds_completed: int
    vocabulary_richness_avg: int | None


class LinguisticVersatilitySessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    score: int | None
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: LinguisticVersatilityMetricsOutput
    rounds: list[LinguisticVersatilityRoundOutput]


class LinguisticVersatilitySessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    score: int | None
    status: Literal["active", "completed", "aborted"]
    mode: Literal["guided", "free"]
    rounds_total: int
    rounds_completed: int
    vocabulary_richness_avg: int | None
