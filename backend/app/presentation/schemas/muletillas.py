from pydantic import BaseModel


class MuletillaDetectedSchema(BaseModel):
    word: str
    count: int
    severity: str
    suggestion: str


class MuletillasEvaluationResponse(BaseModel):
    overall_score: float
    fluency_score: float
    muletillas_score: float
    total_muletillas_count: int
    muletillas_per_minute: float
    muletillas_detected: list[MuletillaDetectedSchema]
    feedback: str
    strengths: str
    improvement_areas: str


class MuletillasSessionRequest(BaseModel):
    question_text: str
    overall_score: float
    fluency_score: float
    muletillas_score: float
    total_muletillas_count: int
    muletillas_per_minute: float
    feedback: str
    strengths: str
    improvement_areas: str
    muletillas_detected: list[MuletillaDetectedSchema]


class MuletillasSessionResponse(BaseModel):
    id: str
    question_text: str
    overall_score: float
    fluency_score: float
    muletillas_score: float
    total_muletillas_count: int
    muletillas_per_minute: float
    feedback: str
    strengths: str
    improvement_areas: str
    created_at: str
    muletillas_detected: list[MuletillaDetectedSchema]


class MuletillasSessionListItem(BaseModel):
    id: str
    question_text: str
    overall_score: float
    total_muletillas_count: int
    created_at: str


class RandomQuestionResponse(BaseModel):
    question: str
