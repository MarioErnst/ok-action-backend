from pydantic import BaseModel, ConfigDict


# --- Request ---

class BlendshapeFrame(BaseModel):
    t: int        # timestamp ms since question start
    pk: float     # mouthPucker
    bd: float     # browDown average
    ld: float     # lipsDown average


class BaselineData(BaseModel):
    pucker: float
    brow_down: float
    lips_down: float


class QuestionPayload(BaseModel):
    question_id: str
    question_text: str
    duration_ms: int
    frames: list[BlendshapeFrame]


class FacialExpressionSessionRequest(BaseModel):
    baseline: BaselineData
    questions: list[QuestionPayload]


# --- Response ---

class QuestionResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: str
    question_text: str
    duration_ms: int
    pucker_score: int
    brow_down_score: int
    lips_down_score: int
    question_score: int


class FacialExpressionSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    overall_score: int
    question_results: list[QuestionResultResponse]
    created_at: str


class FacialExpressionSessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    overall_score: int | None
    created_at: str
