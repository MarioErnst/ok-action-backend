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
