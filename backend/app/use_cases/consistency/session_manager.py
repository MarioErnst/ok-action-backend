from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar


MIN_AUDIO_BYTES = 6400


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_no_audio_analysis() -> dict:
    return {
        "audio_intelligible": False,
        "score": 0,
        "rhythm_consistency_score": 0,
        "volume_consistency_score": 0,
        "clarity_consistency_score": 0,
        "focus_consistency_score": 0,
        "confidence_consistency_score": 0,
        "structure_consistency_score": 0,
        "classification": "not_evaluable",
        "timeline": [],
        "volatility_events": [],
        "strengths": [],
        "improvement_areas": ["Habla durante mas tiempo para poder comparar inicio, medio y cierre."],
        "recommendation": "Graba una respuesta de al menos 30 segundos con una idea central clara.",
        "fb": "No se detecto habla suficiente para evaluar consistencia.",
    }


@dataclass
class ConsistencySessionState:
    user_id: str
    prompt_text: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stop_reason: str | None = None
    analysis: dict | None = None

    MAX_DURATION_SEC: ClassVar[int] = 120
    WARNING_SCORE: ClassVar[int] = 70
    WARNING_EVENTS: ClassVar[int] = 3

    def elapsed_seconds(self) -> int:
        return int((datetime.now(timezone.utc) - self.started_at).total_seconds())

    def set_analysis(self, analysis: dict) -> None:
        self.analysis = analysis

    def final_score(self) -> float | None:
        if not self.analysis:
            return None
        return float(_as_int(self.analysis.get("score"), 0))

    def warning_reason(self) -> str | None:
        if not self.analysis:
            return "analysis_unavailable"

        if self.analysis.get("audio_intelligible") is False:
            return "audio_not_intelligible"

        score = _as_int(self.analysis.get("score"), 100)
        events = self.analysis.get("volatility_events") or []

        if score < self.WARNING_SCORE:
            return "low_consistency_score"

        if len(events) >= self.WARNING_EVENTS:
            return "consistency_breaks_detected"

        return None
