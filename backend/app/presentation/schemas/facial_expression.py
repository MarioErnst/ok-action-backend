from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FacialExpressionMetricsInput(BaseModel):
    """Aggregated emotion distribution submitted by the client.

    Frontend computes the 7 percentages from its own emotion timeline before
    sending; the backend persists them as-is and derives top_emotion and
    expressiveness_score from these values.
    """

    happy_pct: int = Field(ge=0, le=100)
    sad_pct: int = Field(ge=0, le=100)
    angry_pct: int = Field(ge=0, le=100)
    surprised_pct: int = Field(ge=0, le=100)
    fearful_pct: int = Field(ge=0, le=100)
    disgusted_pct: int = Field(ge=0, le=100)
    neutral_pct: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_pct_sum(self) -> "FacialExpressionMetricsInput":
        total = (
            self.happy_pct
            + self.sad_pct
            + self.angry_pct
            + self.surprised_pct
            + self.fearful_pct
            + self.disgusted_pct
            + self.neutral_pct
        )
        if total != 100:
            raise ValueError(
                f"emotion percentages must sum to 100, got {total}"
            )
        return self


class FacialExpressionMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    happy_pct: int
    sad_pct: int
    angry_pct: int
    surprised_pct: int
    fearful_pct: int
    disgusted_pct: int
    neutral_pct: int
    expressiveness_score: int
    top_emotion: Literal[
        "happy", "sad", "angry", "surprised", "fearful", "disgusted", "neutral"
    ]


class FacialExpressionSessionCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    metrics: FacialExpressionMetricsInput

    @model_validator(mode="after")
    def validate_time_range(self) -> "FacialExpressionSessionCreate":
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be greater than started_at")
        return self


class FacialExpressionSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: FacialExpressionMetricsOutput


class FacialExpressionSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    top_emotion: Literal[
        "happy", "sad", "angry", "surprised", "fearful", "disgusted", "neutral"
    ]
    expressiveness_score: int
