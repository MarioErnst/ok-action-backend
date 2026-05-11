from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_BODY_EXPRESSION_DURATION_MS = 20_000

BodyFramingMode = Literal["upper_body", "full_body", "mixed"]
FeedbackSource = Literal["gemini", "rules"]


class BodyExpressionMetricsInput(BaseModel):
    posture_score: int = Field(ge=0, le=100)
    openness_score: int = Field(ge=0, le=100)
    gesture_score: int = Field(ge=0, le=100)
    stability_score: int = Field(ge=0, le=100)
    energy_score: int = Field(ge=0, le=100)
    framing_score: int = Field(ge=0, le=100)
    tracked_pct: int = Field(ge=0, le=100)
    hands_visible_pct: int = Field(ge=0, le=100)
    excessive_movement_pct: int = Field(ge=0, le=100)
    calibration_quality_pct: int = Field(ge=0, le=100)
    framing_mode: BodyFramingMode

    @model_validator(mode="after")
    def validate_tracking_quality(self) -> "BodyExpressionMetricsInput":
        if self.tracked_pct < 40:
            raise ValueError("tracked_pct must be at least 40 to persist the session")
        return self


class BodyExpressionFeedbackOutput(BaseModel):
    summary: str
    strengths: list[str]
    improvements: list[str]
    recommendation: str
    source: FeedbackSource


class BodyExpressionMetricsOutput(BodyExpressionMetricsInput):
    model_config = ConfigDict(from_attributes=True)


class BodyExpressionSessionCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    prompt_text: str | None = Field(default=None, max_length=500)
    metrics: BodyExpressionMetricsInput
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_session_consistency(self) -> "BodyExpressionSessionCreate":
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be greater than started_at")
        duration_ms = int((self.ended_at - self.started_at).total_seconds() * 1000)
        if duration_ms < MIN_BODY_EXPRESSION_DURATION_MS:
            raise ValueError("body expression sessions must last at least 20 seconds")
        return self


class BodyExpressionSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: BodyExpressionMetricsOutput
    feedback: BodyExpressionFeedbackOutput


class BodyExpressionSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    posture_score: int
    gesture_score: int
    stability_score: int
    framing_mode: BodyFramingMode
