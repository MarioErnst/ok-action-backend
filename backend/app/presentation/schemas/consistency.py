from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# HTTP outputs (the WebSocket lifecycle uses its own JSON protocol on the wire)


class ConsistencyMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    consistency_score: int
    volatility_score: int
    active_pct: int


class ConsistencySessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: ConsistencyMetricsOutput


class ConsistencySessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    consistency_score: int
    volatility_score: int
    active_pct: int
