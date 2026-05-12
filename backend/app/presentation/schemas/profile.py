from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


# Supported time ranges for /api/profile/timeline. "all" means no lower bound.
TimeRange = Literal["7d", "30d", "90d", "all"]


class TimelinePoint(BaseModel):
    """One day of aggregated activity for the timeline charts."""

    date: date
    avg_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Average of `sessions.score` for the day; null when no scored sessions.",
    )
    total_duration_ms: int = Field(ge=0)
    session_count: int = Field(ge=0)


class TimelineResponse(BaseModel):
    """Response for GET /api/profile/timeline."""

    range: TimeRange
    # "all" aggregates across every module; otherwise a ModuleEnum value.
    module: str
    daily: list[TimelinePoint]
