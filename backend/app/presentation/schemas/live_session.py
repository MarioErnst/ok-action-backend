from pydantic import BaseModel


class LiveSessionResponse(BaseModel):
    """Full response shape for a saved live session record."""

    id: str
    selected_dims: list[str]
    overall_score: float | None
    total_errors: int
    duration_seconds: int
    stop_reason: str
    created_at: str


class LiveSessionListItem(BaseModel):
    """Abbreviated shape used in list endpoints."""

    id: str
    selected_dims: list[str]
    overall_score: float | None
    stop_reason: str
    created_at: str
