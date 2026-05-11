from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# Inputs


class AbandonSessionRequest(BaseModel):
    """Reason for cutting a live session short. The 'completed' value is
    reserved for the finalize endpoint and rejected here so abandon and
    finalize stay semantically distinct."""

    stop_reason: Literal["user_stop", "time_limit", "error"]


# Outputs


class StartSessionResponse(BaseModel):
    session_id: UUID
    started_at: datetime


class FinalizeSessionResponse(BaseModel):
    session_id: UUID
    status: Literal["completed"]
    score: int | None
    children_count: int


class LiveChildOutput(BaseModel):
    """One component module session that belongs to this live composition."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    module: str
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    score: int | None
    status: Literal["active", "completed", "aborted"]


class LiveMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stop_reason: Literal["user_stop", "time_limit", "error", "completed"]


class LiveSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    score: int | None
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: LiveMetricsOutput | None
    children: list[LiveChildOutput]


class LiveSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    score: int | None
    status: Literal["active", "completed", "aborted"]
    children_count: int
    stop_reason: Literal["user_stop", "time_limit", "error", "completed"] | None


class ComposedAudioEvaluationResponse(BaseModel):
    """Output of POST /live/sessions/{id}/audio-evaluation.

    audio_intelligible mirrors what Gemini reported on the audio gate. If
    false, children is empty and no metrics rows were persisted. evaluation
    is the raw Gemini response with one section per requested module; the
    client uses it to render the summary screen without making extra GETs
    for each child."""

    audio_intelligible: bool
    children: list[LiveChildOutput]
    evaluation: dict[str, Any]
