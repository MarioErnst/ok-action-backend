from pydantic import BaseModel


class ExerciseResultRequest(BaseModel):
    exercise_id: str
    exercise_type: str
    avg_hz: float
    stability: float
    breaks: int
    in_range: bool


class PhonationSessionRequest(BaseModel):
    overall_score: float
    avg_hz: float
    observations: list[str]
    exercises: list[ExerciseResultRequest]


class ExerciseResultResponse(BaseModel):
    id: str
    exercise_id: str
    exercise_type: str
    avg_hz: float
    stability: float
    breaks: int
    in_range: bool


class PhonationSessionResponse(BaseModel):
    id: str
    overall_score: float
    avg_hz: float
    observations: list[str]
    created_at: str
    exercises: list[ExerciseResultResponse]


class PhonationSessionListItem(BaseModel):
    id: str
    overall_score: float
    avg_hz: float
    created_at: str
