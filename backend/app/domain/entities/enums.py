import enum


class ModuleEnum(str, enum.Enum):
    phonation = "phonation"
    loudness = "loudness"
    accentuation = "accentuation"
    pronunciation = "pronunciation"
    muletillas = "muletillas"
    pauses = "pauses"
    precision = "precision"
    linguistic_versatility = "linguistic_versatility"
    facial_expression = "facial_expression"
    body_expression = "body_expression"
    fluency = "fluency"
    consistency = "consistency"
    live = "live"


class SessionStatusEnum(str, enum.Enum):
    active = "active"
    completed = "completed"
    aborted = "aborted"


class StopReasonEnum(str, enum.Enum):
    user_stop = "user_stop"
    time_limit = "time_limit"
    error = "error"
    completed = "completed"
    auto_stop_strikes = "auto_stop_strikes"
    auto_stop_emotion = "auto_stop_emotion"
    auto_stop_loudness = "auto_stop_loudness"
    auto_stop_phonation = "auto_stop_phonation"


class ExerciseTypeEnum(str, enum.Enum):
    holding = "holding"
    gliding = "gliding"


class TopEmotionEnum(str, enum.Enum):
    happy = "happy"
    sad = "sad"
    angry = "angry"
    surprised = "surprised"
    fearful = "fearful"
    disgusted = "disgusted"
    neutral = "neutral"


class BodyFramingModeEnum(str, enum.Enum):
    upper_body = "upper_body"
    full_body = "full_body"
    mixed = "mixed"


class PrecisionModeEnum(str, enum.Enum):
    standalone = "standalone"
    live = "live"


class LinguisticVersatilityModeEnum(str, enum.Enum):
    guided = "guided"
    free = "free"


class MuletillaSeverityEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
