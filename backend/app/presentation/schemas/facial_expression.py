from pydantic import BaseModel, ConfigDict


# --- Request ---

class BlendshapeFrame(BaseModel):
    """Single face detection frame: abbreviated fields to minimize JSON payload across high-frequency captures."""

    t: int        # timestamp ms since question start
    pk: float     # mouthPucker
    bd: float     # browDown average
    ld: float     # lipsDown average


class BaselineData(BaseModel):
    """User's neutral face blendshape baseline captured at session start for deviation scoring."""

    pucker: float
    brow_down: float
    lips_down: float


class QuestionPayload(BaseModel):
    """Raw frame data captured during one question in a facial expression session."""

    question_id: str
    question_text: str
    duration_ms: int
    frames: list[BlendshapeFrame]


class FacialExpressionSessionRequest(BaseModel):
    """Request payload: baseline data + raw frame captures per question."""

    baseline: BaselineData
    questions: list[QuestionPayload]


# --- Response ---

class QuestionResultResponse(BaseModel):
    """Computed scores for a single question: per-expression and composite score."""

    model_config = ConfigDict(from_attributes=True)

    question_id: str
    question_text: str
    duration_ms: int
    pucker_score: int
    brow_down_score: int
    lips_down_score: int
    question_score: int


class FacialExpressionSessionResponse(BaseModel):
    """Full session response: overall score and per-question results computed by backend."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    overall_score: int
    question_results: list[QuestionResultResponse]
    created_at: str


class FacialExpressionSessionListItem(BaseModel):
    """Summary of a facial expression session for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    overall_score: int | None
    created_at: str
