from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AccentuationPhraseOutput(BaseModel):
    """One prompt from the accentuation catalog.

    `category` carries the sentence-type tag (declarative / interrogative /
    exclamative) that the UI uses to badge each phrase.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str
    category: str


# Per-phrase Gemini evaluation (ephemeral, never persisted)


class PhraseSpecificError(BaseModel):
    word: str
    expected_stress: str
    actual_issue: str
    suggestion: str


class PhraseEvaluation(BaseModel):
    phrase_text: str
    phrase_index: int
    overall_score: int = Field(ge=0, le=100)
    pronunciation_score: int = Field(ge=0, le=100)
    rhythm_score: int = Field(ge=0, le=100)
    intonation_score: int = Field(ge=0, le=100)
    stress_score: int = Field(ge=0, le=100)
    feedback: str
    specific_errors: list[PhraseSpecificError]


# Persisted session metrics


class AccentuationMetricsInput(BaseModel):
    pronunciation_score: int = Field(ge=0, le=100)
    rhythm_score: int = Field(ge=0, le=100)
    intonation_score: int = Field(ge=0, le=100)
    stress_score: int = Field(ge=0, le=100)
    phrases_count: int = Field(ge=1)


class AccentuationMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pronunciation_score: int
    rhythm_score: int
    intonation_score: int
    stress_score: int
    phrases_count: int


class AccentuationPhraseEvaluationInput(BaseModel):
    """One persisted phrase evaluation for the session.

    The client sends the prompt_id (from the catalog) plus the four sub-scores
    Gemini returned during /evaluate. Ephemeral fields (feedback, specific
    errors, text) stay out — they do not belong in the DB.
    """

    phrase_index: int = Field(ge=0)
    prompt_id: UUID
    pronunciation_score: int = Field(ge=0, le=100)
    rhythm_score: int = Field(ge=0, le=100)
    intonation_score: int = Field(ge=0, le=100)
    stress_score: int = Field(ge=0, le=100)


class AccentuationPhraseEvaluationOutput(BaseModel):
    """Per-phrase row returned by the detail endpoint.

    Includes the prompt text and category so the UI can render the phrase
    without an extra catalog round-trip.
    """

    model_config = ConfigDict(from_attributes=True)

    phrase_index: int
    prompt_id: UUID
    prompt_text: str
    prompt_category: str
    pronunciation_score: int
    rhythm_score: int
    intonation_score: int
    stress_score: int


class AccentuationWeakestPromptOutput(BaseModel):
    """One row of the weakest-prompts insights endpoint.

    `avg_score` is the average of the four sub-scores across every
    evaluation of this prompt by the user. `practice_count` is the number
    of times the prompt has been evaluated; UIs typically hide entries
    below a minimum practice count to avoid noise.
    """

    prompt_id: UUID
    text: str
    category: str
    avg_score: int = Field(ge=0, le=100)
    practice_count: int = Field(ge=1)


class AccentuationSessionCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    metrics: AccentuationMetricsInput
    phrases: list[AccentuationPhraseEvaluationInput] = Field(default_factory=list)
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_session_consistency(self) -> "AccentuationSessionCreate":
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be greater than started_at")
        if len(self.phrases) != self.metrics.phrases_count:
            raise ValueError(
                "metrics.phrases_count must equal the length of phrases"
            )
        indexes = [p.phrase_index for p in self.phrases]
        if len(set(indexes)) != len(indexes):
            raise ValueError("phrase_index must be unique within phrases")
        for index in indexes:
            if index >= self.metrics.phrases_count:
                raise ValueError(
                    "phrase_index must be < metrics.phrases_count"
                )
        return self


class AccentuationSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: AccentuationMetricsOutput


class AccentuationSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    phrases_count: int
