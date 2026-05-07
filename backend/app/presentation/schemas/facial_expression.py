from pydantic import BaseModel, ConfigDict, Field


# --- Limits ---
# MediaPipe blendshape values are normalized [0.0, 1.0]. Reject anything outside
# that range to prevent corrupted captures from skewing scoring.
# Frame and question caps prevent memory exhaustion through oversized payloads.
MAX_FRAMES_PER_QUESTION = 18_000   # ~20 minutes at 15fps; far above any normal session
MAX_QUESTIONS_PER_SESSION = 50
MAX_QUESTION_TEXT_LEN = 1000
MAX_DURATION_MS = 600_000           # 10 minutes per question


# --- Request ---

class BlendshapeFrame(BaseModel):
    """Single face detection frame: abbreviated fields to minimize JSON payload across high-frequency captures."""

    t: int = Field(ge=0)               # timestamp ms since question start
    pk: float = Field(ge=0.0, le=1.0)  # mouthPucker
    bd: float = Field(ge=0.0, le=1.0)  # browDown average
    ld: float = Field(ge=0.0, le=1.0)  # lipsDown average


class BaselineData(BaseModel):
    """User's neutral face blendshape baseline captured at session start for deviation scoring."""

    pucker: float = Field(ge=0.0, le=1.0)
    brow_down: float = Field(ge=0.0, le=1.0)
    lips_down: float = Field(ge=0.0, le=1.0)


class QuestionPayload(BaseModel):
    """Raw frame data captured during one question in a facial expression session."""

    question_id: str = Field(min_length=1, max_length=50)
    question_text: str = Field(min_length=1, max_length=MAX_QUESTION_TEXT_LEN)
    duration_ms: int = Field(ge=0, le=MAX_DURATION_MS)
    frames: list[BlendshapeFrame] = Field(max_length=MAX_FRAMES_PER_QUESTION)


class FacialExpressionSessionRequest(BaseModel):
    """Request payload: baseline data + raw frame captures per question."""

    baseline: BaselineData
    questions: list[QuestionPayload] = Field(min_length=1, max_length=MAX_QUESTIONS_PER_SESSION)


# --- Response ---

class QuestionResultResponse(BaseModel):
    """Computed scores for a single question: per-expression and composite score.

    Scores are nullable so callers can distinguish missing data from a zero score.
    """

    model_config = ConfigDict(from_attributes=True)

    question_id: str
    question_text: str
    duration_ms: int
    pucker_score: int | None
    brow_down_score: int | None
    lips_down_score: int | None
    question_score: int | None


class FacialExpressionSessionResponse(BaseModel):
    """Full session response: overall score and per-question results computed by backend."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    overall_score: int | None
    question_results: list[QuestionResultResponse]
    created_at: str


class FacialExpressionSessionListItem(BaseModel):
    """Summary of a facial expression session for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    overall_score: int | None
    created_at: str
