from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar


@dataclass
class LiveSessionState:
    """
    In-memory state for a single live session WebSocket connection.
    Accumulates analysis cycles and evaluates stop conditions.
    """

    user_id: str
    selected_dims: list[str]
    accumulated_errors: int = 0
    analyses: list[dict] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stop_reason: str | None = None
    # Populated only when 'lex' is in selected_dims and the end-of-session
    # versatility evaluation completes successfully. Persisted as-is in
    # LiveSession.lex_result.
    lex_result: dict | None = None

    # ClassVar prevents these from becoming dataclass fields (no accidental override at construction)
    MAX_DURATION_SEC: ClassVar[int] = 300
    MAX_ERRORS: ClassVar[int] = 3
    MIN_SCORE: ClassVar[int] = 70

    def elapsed_seconds(self) -> int:
        """Returns the number of seconds since the session started."""
        return int((datetime.now(timezone.utc) - self.started_at).total_seconds())

    def average_overall(self) -> float | None:
        """Returns the average overall score across all cycles, or None if no cycles ran."""
        if not self.analyses:
            return None
        scores = [a.get("overall", 0) for a in self.analyses]
        return round(sum(scores) / len(scores), 2)

    def evaluate_thresholds(self, analysis: dict) -> tuple[bool, str, str | None]:
        """
        Accumulates errors from selected dims, appends the analysis, then checks all stop conditions.
        Returns (should_stop, reason, failing_dim).
        Evaluation order: low_score first, then error_threshold, then time_limit.
        """
        for dim in self.selected_dims:
            dim_data = analysis.get("dims", {}).get(dim, {})
            errors = dim_data.get("err") or dim_data.get("det") or []
            self.accumulated_errors += len(errors)

        self.analyses.append(analysis)

        for dim in self.selected_dims:
            score = analysis.get("dims", {}).get(dim, {}).get("sc", 100)
            if score < self.MIN_SCORE:
                return True, "low_score", dim

        if self.accumulated_errors >= self.MAX_ERRORS:
            return True, "error_threshold", None

        if self.elapsed_seconds() >= self.MAX_DURATION_SEC:
            return True, "time_limit", None

        return False, "", None
