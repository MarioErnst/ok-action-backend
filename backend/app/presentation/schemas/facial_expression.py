from pydantic import BaseModel, ConfigDict, Field

# --- Limits ---
# An "event" is recorded only when the dominant emotion changes, so realistic
# sessions produce tens to a few hundred events. The cap protects against
# malicious payloads while still allowing very long or rapidly-changing sessions.
MAX_EVENTS_PER_SESSION = 5000
MAX_DURATION_MS = 30 * 60 * 1000  # 30 minutes
MAX_GESTURE_KEYS = 60             # there are 52 ARKit blendshapes; 60 is a soft cap


# --- Allowed values ---
# Server-side allow-list keeps the database column clean and lets the frontend
# add new emotions without the backend silently accepting typos.
ALLOWED_EMOTIONS = {"happy", "sad", "angry", "surprise", "fear", "disgust", "neutral"}


# --- Request ---

class EmotionEventInput(BaseModel):
    """One detected change of dominant emotion within a session."""

    t_ms: int = Field(ge=0, le=MAX_DURATION_MS)
    emotion: str = Field(min_length=1, max_length=20)
    # gestures is a free-form map of gesture_id -> intensity 0..1; we cap the
    # number of keys to avoid unbounded JSON growth from a malicious client.
    gestures: dict[str, float] = Field(default_factory=dict, max_length=MAX_GESTURE_KEYS)


class SessionCreateRequest(BaseModel):
    """Persist a completed facial-expression analysis session."""

    duration_ms: int = Field(ge=0, le=MAX_DURATION_MS)
    events: list[EmotionEventInput] = Field(default_factory=list, max_length=MAX_EVENTS_PER_SESSION)


# --- Response ---

class EmotionEventResponse(BaseModel):
    """Single event in the saved session."""

    model_config = ConfigDict(from_attributes=True)

    t_ms: int
    emotion: str
    gestures: dict[str, float]


class SessionDetailResponse(BaseModel):
    """Full session with computed distribution and event timeline."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    duration_ms: int
    dominant_emotion: str | None
    dominant_percentage: int | None
    emotion_distribution: dict[str, int]
    created_at: str
    events: list[EmotionEventResponse]


class SessionListItem(BaseModel):
    """Summary for the sessions list."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    duration_ms: int
    dominant_emotion: str | None
    dominant_percentage: int | None
    created_at: str
