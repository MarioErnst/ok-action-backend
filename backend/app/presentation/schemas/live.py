from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Inputs


class AbandonSessionRequest(BaseModel):
    """Reason for cutting a live session short via the abandon endpoint.
    The 'completed' value is reserved for the finalize endpoint. The
    'auto_stop_strikes' and 'auto_stop_emotion' values flow through
    finalize (not abandon), because they include a regular score
    computation; abandon stays for orphan cleanup and explicit user-
    initiated cuts."""

    stop_reason: Literal["user_stop", "time_limit", "error"]


class FinalizeSessionRequest(BaseModel):
    """Optional body for the finalize endpoint. When auto_stop_reason is
    present, the session is marked aborted with that reason instead of
    completed. Omit the body (or pass auto_stop_reason=None) for the
    standard natural-completion case."""

    auto_stop_reason: Literal["auto_stop_strikes", "auto_stop_emotion"] | None = None


class FacialSummaryInput(BaseModel):
    """Aggregate emotion percentages computed in the browser from the
    facial emotion classifier stream during a live session. Submitted
    alongside the audio in the composed evaluation request when
    facial_expression is among the selected modules.

    The seven percentages must each fall in 0..100. The backend
    re-normalizes them so they sum exactly to 100 before persisting
    (the BD CHECK constraint requires it), so the client does not need
    to be perfect; this validator only guards against grossly invalid
    input."""

    happy_pct: int = Field(ge=0, le=100)
    sad_pct: int = Field(ge=0, le=100)
    angry_pct: int = Field(ge=0, le=100)
    surprised_pct: int = Field(ge=0, le=100)
    fearful_pct: int = Field(ge=0, le=100)
    disgusted_pct: int = Field(ge=0, le=100)
    neutral_pct: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _at_least_one_nonzero(self) -> "FacialSummaryInput":
        total = (
            self.happy_pct + self.sad_pct + self.angry_pct + self.surprised_pct
            + self.fearful_pct + self.disgusted_pct + self.neutral_pct
        )
        if total == 0:
            raise ValueError("at least one emotion percentage must be > 0")
        return self


# Outputs


class StartSessionResponse(BaseModel):
    session_id: UUID
    started_at: datetime


class FinalizeSessionResponse(BaseModel):
    session_id: UUID
    status: Literal["completed", "aborted"]
    score: int | None
    children_count: int
    stop_reason: Literal[
        "completed",
        "auto_stop_strikes",
        "auto_stop_emotion",
    ]


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

    stop_reason: Literal[
        "user_stop",
        "time_limit",
        "error",
        "completed",
        "auto_stop_strikes",
        "auto_stop_emotion",
    ]


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
    stop_reason: Literal[
        "user_stop",
        "time_limit",
        "error",
        "completed",
        "auto_stop_strikes",
        "auto_stop_emotion",
    ] | None


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


# Frame evaluation (streaming during the session)


class FrameMuletillaItem(BaseModel):
    word: str
    count: int
    severity: Literal["low", "medium", "high"]
    timestamp_ms: int


class FrameMuletillasSection(BaseModel):
    total: int
    detected: list[FrameMuletillaItem]


class FrameAccentuationSection(BaseModel):
    pronunciation_score: int
    rhythm_score: int
    intonation_score: int
    stress_score: int


class FramePronunciationSection(BaseModel):
    vowel_score: int
    consonant_score: int
    fluency_score: int
    intelligibility_score: int


class FrameEvaluationResponse(BaseModel):
    """Output of POST /live/sessions/{id}/evaluate-frame.

    Only the sections of requested audio modules are present. The
    client feeds the contents into the strike counter directly: each
    detected muletilla bumps the counter, and an accentuation/
    pronunciation section with any score below 55 contributes one
    strike capped per frame."""

    frame_index: int
    evaluated_until_seconds: int
    muletillas: FrameMuletillasSection | None = None
    accentuation: FrameAccentuationSection | None = None
    pronunciation: FramePronunciationSection | None = None
