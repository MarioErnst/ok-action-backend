from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class FluencySessionState:
    user_id: str
    prompt_text: str
    analyses: list[dict] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stop_reason: str | None = None

    MAX_DURATION_SEC: ClassVar[int] = 120
    WARNING_SCORE: ClassVar[int] = 70
    WARNING_EVENTS: ClassVar[int] = 3

    def elapsed_seconds(self) -> int:
        return int((datetime.now(timezone.utc) - self.started_at).total_seconds())

    def average_score(self) -> float | None:
        if not self.analyses:
            return None
        scores = [_as_int(analysis.get("score"), 0) for analysis in self.analyses]
        return round(sum(scores) / len(scores), 2)

    def evaluate_attention(self, analysis: dict) -> tuple[bool, str | None]:
        self.analyses.append(analysis)

        if analysis.get("audio_intelligible") is False:
            return True, "audio_not_intelligible"

        score = _as_int(analysis.get("score"), 100)
        prompt_alignment_score = _as_int(analysis.get("prompt_alignment_score"), 100)
        stuck_events = analysis.get("stuck_events") or []
        repetitions = _as_int(analysis.get("repetitions"), 0)
        restarts = _as_int(analysis.get("restarts"), 0)
        long_blocks = _as_int(analysis.get("long_blocks"), 0)
        event_count = len(stuck_events) + repetitions + restarts + long_blocks

        if self.elapsed_seconds() >= self.MAX_DURATION_SEC:
            self.stop_reason = "time_limit"
            return True, "time_limit"

        if prompt_alignment_score < self.WARNING_SCORE:
            return True, "not_aligned_with_prompt"

        if score < self.WARNING_SCORE:
            return True, "low_fluency_score"

        if event_count >= self.WARNING_EVENTS:
            return True, "fluency_blocks_detected"

        return False, None
