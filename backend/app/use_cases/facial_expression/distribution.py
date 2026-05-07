"""Compute the time-weighted emotion distribution for a session.

Each event marks the moment a new emotion *began*, so the time spent in any
given emotion is the gap between consecutive events (and from the last event to
the end of the session). Percentages are normalized to integers that sum to 100
to avoid the rounding mismatch users notice when bars don't add up.
"""
from __future__ import annotations


def compute_distribution(
    duration_ms: int, events: list[dict]
) -> tuple[dict[str, int], str | None, int | None]:
    """Return (percentages_by_emotion, dominant_emotion, dominant_percentage).

    Args:
        duration_ms: total session length in milliseconds.
        events: list of {"t_ms": int, "emotion": str, ...}, ordered by t_ms ascending.

    Edge cases:
        - duration_ms <= 0: returns ({}, None, None).
        - no events: returns ({}, None, None) — we cannot infer emotion without data.
    """
    if duration_ms <= 0 or not events:
        return {}, None, None

    sorted_events = sorted(events, key=lambda e: e["t_ms"])
    time_per_emotion: dict[str, int] = {}

    for i, ev in enumerate(sorted_events):
        start = ev["t_ms"]
        end = sorted_events[i + 1]["t_ms"] if i + 1 < len(sorted_events) else duration_ms
        elapsed = max(0, end - start)
        time_per_emotion[ev["emotion"]] = time_per_emotion.get(ev["emotion"], 0) + elapsed

    total_tracked = sum(time_per_emotion.values())
    if total_tracked == 0:
        return {}, None, None

    # Largest-remainder rounding so percentages always sum to exactly 100,
    # avoiding the "bars add up to 99" UX bug from naive rounding.
    raw = {k: v * 100 / total_tracked for k, v in time_per_emotion.items()}
    floored = {k: int(v) for k, v in raw.items()}
    remainder = 100 - sum(floored.values())
    fractional = sorted(raw.items(), key=lambda kv: kv[1] - int(kv[1]), reverse=True)
    for k, _ in fractional[:remainder]:
        floored[k] += 1

    dominant_emotion = max(floored, key=floored.get)
    dominant_percentage = floored[dominant_emotion]
    return floored, dominant_emotion, dominant_percentage
