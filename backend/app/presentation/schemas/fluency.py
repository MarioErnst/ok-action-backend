from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# HTTP outputs (the WebSocket lifecycle uses its own JSON protocol on the wire)


class FluencyMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fluency_score: int
    stuck_events_count: int
    words_per_minute: float


class FluencySessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: FluencyMetricsOutput


class FluencySessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    fluency_score: int
    words_per_minute: float
