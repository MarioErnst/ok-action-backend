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
    rounds_total: int = Field(ge=1, le=20)


class StartSessionResponse(BaseModel):
    session_id: UUID
    started_at: datetime
    rounds_total: int
    prompts: list[PromptOut]


class EvaluateRoundRequestForm(BaseModel):
    """Documentation-only mirror of the multipart Form fields handled in the
    router. FastAPI does not support nested Pydantic models for multipart, so
    the router declares each field with Form(...) directly."""

    round_index: int = Field(ge=0)
    prompt_id: UUID


class EvaluateRoundResponse(BaseModel):
    """Per-round evaluation result. Carries Gemini's transcript and feedback
    text for ephemeral display in the UI; only scores and is_audio_intelligible
    are persisted."""

    round_index: int
    prompt_id: UUID
    is_audio_intelligible: bool
    score: int | None = Field(default=None, ge=0, le=100)
    relevance_score: int | None = Field(default=None, ge=0, le=100)
    directness_score: int | None = Field(default=None, ge=0, le=100)
    conciseness_score: int | None = Field(default=None, ge=0, le=100)
    transcript: str
    feedback: str
    strengths: list[str]
    improvement_areas: list[str]


class FinalizeSessionResponse(BaseModel):
    session_id: UUID
    status: Literal["completed", "aborted"]
    score: int | None
    rounds_completed: int
    rounds_total: int
    relevance_score: int | None
    directness_score: int | None
    conciseness_score: int | None


# Persisted detail


class PrecisionRoundOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    round_index: int
    prompt_id: UUID
    score: int | None
    relevance_score: int | None
    directness_score: int | None
    conciseness_score: int | None
    is_audio_intelligible: bool


class PrecisionMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mode: Literal["standalone", "live"]
    rounds_total: int
    rounds_completed: int
    relevance_score: int | None
    directness_score: int | None
    conciseness_score: int | None


class PrecisionSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    score: int | None
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: PrecisionMetricsOutput
    rounds: list[PrecisionRoundOutput]


class PrecisionSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    score: int | None
    status: Literal["active", "completed", "aborted"]
    rounds_total: int
    rounds_completed: int
