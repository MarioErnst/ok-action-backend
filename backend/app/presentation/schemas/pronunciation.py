from pydantic import BaseModel


class PhonemeErrorSchema(BaseModel):
    phoneme: str
    word: str
    actual_issue: str
    suggestion: str


class PhrasePronunciationResponse(BaseModel):
    phrase_text: str
    phrase_index: int
    overall_score: float
    vowel_score: float
    consonant_score: float
    fluency_score: float
    intelligibility_score: float
    feedback: str
    phoneme_errors: list[PhonemeErrorSchema]


class SavePhrasePronunciationDto(BaseModel):
    phrase_text: str
    phrase_index: int
    overall_score: float
    vowel_score: float
    consonant_score: float
    fluency_score: float
    intelligibility_score: float
    feedback: str
    phoneme_errors: list[PhonemeErrorSchema]


class PronunciationSessionRequest(BaseModel):
    level: str
    overall_score: float
    vowel_score: float
    consonant_score: float
    fluency_score: float
    intelligibility_score: float
    summary_feedback: str
    evaluations: list[SavePhrasePronunciationDto]


class PronunciationSessionResponse(BaseModel):
    id: str
    level: str
    overall_score: float
    vowel_score: float
    consonant_score: float
    fluency_score: float
    intelligibility_score: float
    summary_feedback: str
    created_at: str
    evaluations: list[PhrasePronunciationResponse]


class PronunciationSessionListItem(BaseModel):
    id: str
    level: str
    overall_score: float
    created_at: str
