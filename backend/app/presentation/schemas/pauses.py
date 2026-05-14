from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PauseMetricsInput(BaseModel):
    pauses_count: int = Field(ge=0)
    total_pause_ms: int = Field(ge=0)
    longest_pause_ms: int = Field(ge=0)
    silence_pct: int = Field(ge=0, le=100)
    prompt_id: UUID | None = None

    @model_validator(mode="after")
    def validate_internal_consistency(self) -> "PauseMetricsInput":
        if self.pauses_count == 0:
            if self.total_pause_ms != 0 or self.longest_pause_ms != 0:
                raise ValueError(
                    "with pauses_count=0, total_pause_ms and longest_pause_ms must be 0"
                )
        if self.longest_pause_ms > self.total_pause_ms:
            raise ValueError(
                "longest_pause_ms cannot exceed total_pause_ms"
            )
        return self


class PauseMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pauses_count: int
    total_pause_ms: int
    longest_pause_ms: int
    silence_pct: int
    prompt_id: UUID | None = None


class PausePromptOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str


class PauseSessionCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    score: int = Field(ge=0, le=100)
    metrics: PauseMetricsInput
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_session_consistency(self) -> "PauseSessionCreate":
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be greater than started_at")
        duration_ms = int((self.ended_at - self.started_at).total_seconds() * 1000)
        if self.metrics.total_pause_ms > duration_ms:
            raise ValueError(
                "total_pause_ms cannot exceed the session duration"
            )
        return self


class PauseSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: PauseMetricsOutput


class PauseSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    pauses_count: int
    silence_pct: int
