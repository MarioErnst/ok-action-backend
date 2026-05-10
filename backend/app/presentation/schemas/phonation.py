from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Inputs


class PhonationExerciseInput(BaseModel):
    exercise_type: Literal["holding", "gliding"]
    avg_hz: float = Field(gt=0)
    stability_score: int = Field(ge=0, le=100)
    breaks_count: int = Field(ge=0)
    in_range_pct: int = Field(ge=0, le=100)


class PhonationMetricsInput(BaseModel):
    avg_hz: float = Field(gt=0)
    stability_score: int = Field(ge=0, le=100)
    breaks_count: int = Field(ge=0)
    exercises_count: int = Field(ge=1)


class PhonationSessionCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    score: int = Field(ge=0, le=100)
    metrics: PhonationMetricsInput
    exercises: list[PhonationExerciseInput] = Field(min_length=1)
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_consistency(self) -> "PhonationSessionCreate":
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be greater than started_at")
        if self.metrics.exercises_count != len(self.exercises):
            raise ValueError(
                "metrics.exercises_count must equal the number of exercises"
            )
        seen_types: set[str] = set()
        for exercise in self.exercises:
            if exercise.exercise_type in seen_types:
                raise ValueError(
                    f"duplicated exercise_type '{exercise.exercise_type}'; one row per type"
                )
            seen_types.add(exercise.exercise_type)
        return self


# Outputs


class PhonationExerciseOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exercise_type: Literal["holding", "gliding"]
    avg_hz: float
    stability_score: int
    breaks_count: int
    in_range_pct: int


class PhonationMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    avg_hz: float
    stability_score: int
    breaks_count: int
    exercises_count: int


class PhonationSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: PhonationMetricsOutput
    exercises: list[PhonationExerciseOutput]


class PhonationSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    avg_hz: float
