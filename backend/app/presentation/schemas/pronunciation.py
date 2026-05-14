from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PronunciationPhraseOutput(BaseModel):
    """One prompt from the pronunciation catalog.

    `difficulty` carries the level label (basico / intermedio / avanzado) the
    UI uses to group phrases. The same value is sent back as `level` in
    PronunciationMetricsInput when persisting a completed session.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str
    difficulty: str


# Per-phrase Gemini evaluation (ephemeral, never persisted)


class PhonemeError(BaseModel):
    phoneme: str
    word: str
    actual_issue: str
    suggestion: str


class PhraseEvaluation(BaseModel):
    phrase_text: str
    phrase_index: int
    overall_score: int = Field(ge=0, le=100)
    vowel_score: int = Field(ge=0, le=100)
    consonant_score: int = Field(ge=0, le=100)
    fluency_score: int = Field(ge=0, le=100)
    intelligibility_score: int = Field(ge=0, le=100)
    feedback: str
    phoneme_errors: list[PhonemeError]


# Persisted session metrics


class PronunciationMetricsInput(BaseModel):
    level: str = Field(min_length=1, max_length=20)
    vowel_score: int = Field(ge=0, le=100)
    consonant_score: int = Field(ge=0, le=100)
    fluency_score: int = Field(ge=0, le=100)
    intelligibility_score: int = Field(ge=0, le=100)
    phrases_count: int = Field(ge=1)


class PronunciationMetricsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str
    vowel_score: int
    consonant_score: int
    fluency_score: int
    intelligibility_score: int
    phrases_count: int


class PronunciationPhraseEvaluationInput(BaseModel):
    """One persisted phrase evaluation for the session.

    The client sends the prompt_id (from the catalog) plus the four
    sub-scores Gemini returned during /evaluate. Ephemeral fields (feedback,
    phoneme errors, text) stay out — they do not belong in the DB.
    """

    phrase_index: int = Field(ge=0)
    prompt_id: UUID
    vowel_score: int = Field(ge=0, le=100)
    consonant_score: int = Field(ge=0, le=100)
    fluency_score: int = Field(ge=0, le=100)
    intelligibility_score: int = Field(ge=0, le=100)


class PronunciationPhraseEvaluationOutput(BaseModel):
    """Per-phrase row returned by the detail endpoint."""

    model_config = ConfigDict(from_attributes=True)

    phrase_index: int
    prompt_id: UUID
    prompt_text: str
    prompt_difficulty: str
    vowel_score: int
    consonant_score: int
    fluency_score: int
    intelligibility_score: int


class PronunciationWeakestPromptOutput(BaseModel):
    """One row of the weakest-prompts insights endpoint."""

    prompt_id: UUID
    text: str
    difficulty: str
    avg_score: int = Field(ge=0, le=100)
    practice_count: int = Field(ge=1)


class PronunciationSessionCreate(BaseModel):
    started_at: datetime
    ended_at: datetime
    metrics: PronunciationMetricsInput
    phrases: list[PronunciationPhraseEvaluationInput] = Field(default_factory=list)
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_session_consistency(self) -> "PronunciationSessionCreate":
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


class PronunciationSessionDetail(BaseModel):
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    created_at: datetime
    metrics: PronunciationMetricsOutput


class PronunciationSessionListItem(BaseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    score: int
    status: Literal["active", "completed", "aborted"]
    level: str
    phrases_count: int
