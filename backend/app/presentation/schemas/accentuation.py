from pydantic import BaseModel


class SpecificErrorSchema(BaseModel):
    word: str
    expected_stress: str
    actual_issue: str
    suggestion: str


class PhraseEvaluationResponse(BaseModel):
    phrase_text: str
    phrase_index: int
    overall_score: float
    pronunciation_score: float
    rhythm_score: float
    intonation_score: float
    stress_accuracy_score: float
    feedback: str
    specific_errors: list[SpecificErrorSchema]


class PhraseEvaluationRequest(BaseModel):
    phrase_text: str
    phrase_index: int
    overall_score: float
    pronunciation_score: float
    rhythm_score: float
    intonation_score: float
    stress_accuracy_score: float
    feedback: str
    specific_errors: list[SpecificErrorSchema]


class AccentuationSessionRequest(BaseModel):
    overall_score: float
    pronunciation_score: float
    rhythm_score: float
    intonation_score: float
    stress_accuracy_score: float
    summary_feedback: str
    evaluations: list[PhraseEvaluationRequest]


class AccentuationSessionResponse(BaseModel):
    id: str
    overall_score: float
    pronunciation_score: float
    rhythm_score: float
    intonation_score: float
    stress_accuracy_score: float
    summary_feedback: str
    created_at: str
    evaluations: list[PhraseEvaluationResponse]


class AccentuationSessionListItem(BaseModel):
    id: str
    overall_score: float
    created_at: str
