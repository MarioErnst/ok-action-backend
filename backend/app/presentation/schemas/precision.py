from pydantic import BaseModel


class PrecisionRoundResponse(BaseModel):
    id: str
    question_text: str
    relevance_score: int | None
    directness_score: int | None
    conciseness_score: int | None
    overall_score: int | None
    feedback: str | None
    strengths: list[str] | None
    improvement_areas: list[str] | None
    noise_level: str
    audio_intelligible: bool
    created_at: str


class PrecisionQuestionSchema(BaseModel):
    id: str
    text: str
    category: str
    difficulty_level: str


class StartSessionResponse(BaseModel):
    session_id: str
    questions: list[PrecisionQuestionSchema]
    total_rounds: int


class EvaluateRoundResponse(BaseModel):
    round_id: str
    audio_intelligible: bool
    relevance_score: int | None
    directness_score: int | None
    conciseness_score: int | None
    overall_score: int | None
    feedback: str | None
    strengths: list[str] | None
    improvement_areas: list[str] | None


class FinalizeSessionResponse(BaseModel):
    session_id: str
    overall_score: float | None
    completed_rounds: int
    status: str


class PrecisionSessionResponse(BaseModel):
    id: str
    mode: str
    total_rounds: int
    completed_rounds: int
    overall_score: float | None
    status: str
    created_at: str
    rounds: list[PrecisionRoundResponse]


class PrecisionHistoryItem(BaseModel):
    id: str
    overall_score: float | None
    completed_rounds: int
    total_rounds: int
    status: str
    created_at: str
