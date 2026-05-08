from pydantic import BaseModel, ConfigDict, Field

# --- Limits ---
# Audio is short (one answer per round). 5MB caps a runaway client without
# blocking realistic recordings (~30s mp4 ≈ 250KB; ~30s wav 16kHz mono ≈ 1MB).
MAX_AUDIO_BYTES = 5 * 1024 * 1024


# --- Allowed values ---
ALLOWED_MODES = {"guided", "free"}
ALLOWED_RICHNESS = {1, 2, 3}  # 1=básico, 2=intermedio, 3=avanzado


# --- Request ---

class StartSessionRequest(BaseModel):
    """Open a new guided session. Total rounds is set by the backend based on
    how many active questions are in the database."""

    pass


# Free-mode session creates and finalizes in a single request. The audio is
# uploaded as multipart/form-data, not in the JSON body, so there is no
# request schema for the body itself — the router reads the file directly.


# --- Response ---

class QuestionSchema(BaseModel):
    """Public shape of a versatility question."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    category: str
    difficulty_level: str


class StartSessionResponse(BaseModel):
    """Returned from POST /sessions: id of the new session and questions to ask."""

    session_id: str
    total_rounds: int
    questions: list[QuestionSchema]


class RoundResultResponse(BaseModel):
    """One evaluated answer within a session."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str | None
    question_text: str | None
    versatility_score: int | None = Field(default=None, ge=0, le=100)
    vocabulary_richness: int | None = Field(default=None, ge=1, le=3)
    feedback: str | None
    audio_intelligible: bool
    created_at: str


class EvaluateRoundResponse(BaseModel):
    """Returned after a guided round is uploaded and analyzed."""

    round_id: str
    audio_intelligible: bool
    versatility_score: int | None = Field(default=None, ge=0, le=100)
    vocabulary_richness: int | None = Field(default=None, ge=1, le=3)
    feedback: str | None
    completed_rounds: int
    total_rounds: int


class SessionDetailResponse(BaseModel):
    """Full session with all rounds."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: str
    total_rounds: int
    completed_rounds: int
    overall_score: int | None
    status: str
    created_at: str
    completed_at: str | None
    rounds: list[RoundResultResponse]


class SessionListItem(BaseModel):
    """Summary for the history list."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: str
    overall_score: int | None
    status: str
    created_at: str


class FreeSessionResponse(BaseModel):
    """Returned from POST /free with the single round result inlined."""

    session_id: str
    versatility_score: int | None = Field(default=None, ge=0, le=100)
    vocabulary_richness: int | None = Field(default=None, ge=1, le=3)
    feedback: str | None
    audio_intelligible: bool
