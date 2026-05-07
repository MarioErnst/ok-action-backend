# Minimum deviation above the user's baseline to count a frame as "bad expression".
# Values are calibrated for MediaPipe FaceLandmarker blendshape ranges (0.0–1.0).
THRESHOLDS = {
    "pucker": 0.15,    # mouthPucker — lip puckering
    "brow_down": 0.12, # browDownLeft/Right avg — furrowed brow
    "lips_down": 0.12, # mouthFrownLeft/Right avg — corners down
}

# Contribution of each expression to the per-question composite score.
WEIGHTS = {
    "pucker": 0.40,
    "brow_down": 0.35,
    "lips_down": 0.25,
}

# Fail loudly on import if weights are misconfigured: the composite score
# assumes weights sum to 1.0 to stay within the 0-100 range.
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "WEIGHTS must sum to 1.0"


def score_expression(
    frames: list[dict],
    baseline: float,
    threshold: float,
    key: str,
) -> int:
    """Return 0-100 score for one expression across all frames.

    100 = expression never exceeded threshold above baseline.
    0   = expression was always above threshold.

    Args:
        frames: list of frame dicts containing blendshape values.
        baseline: user's resting value for the expression (captured during calibration).
        threshold: minimum deviation above baseline to count a frame as bad.
        key: dict key in each frame for this expression (e.g. "pk" for pucker).

    Returns:
        Integer score 0-100.
    """
    if not frames:
        return 100
    above = sum(1 for f in frames if (f.get(key, 0.0) - baseline) > threshold)
    bad_ratio = above / len(frames)
    return round((1.0 - bad_ratio) * 100)


def calculate_session_scores(
    baseline: dict,
    questions: list[dict],
) -> dict:
    """Compute per-question and overall scores from raw frame data.

    Args:
        baseline: {"pucker": float, "brow_down": float, "lips_down": float}
        questions: list of {"question_id": str, "frames": list[dict]}
                   Each frame: {"t": int, "pk": float, "bd": float, "ld": float}

    Returns:
        {
            "overall_score": int,
            "question_results": [
                {
                    "question_id": str,
                    "pucker_score": int,
                    "brow_down_score": int,
                    "lips_down_score": int,
                    "question_score": int,
                }
            ]
        }
    """
    question_results = []

    for q in questions:
        frames = q.get("frames", [])

        pucker_score = score_expression(
            frames, baseline["pucker"], THRESHOLDS["pucker"], "pk"
        )
        brow_score = score_expression(
            frames, baseline["brow_down"], THRESHOLDS["brow_down"], "bd"
        )
        lips_score = score_expression(
            frames, baseline["lips_down"], THRESHOLDS["lips_down"], "ld"
        )

        # Weighted composite — pucker carries more weight because it is
        # the strongest visual signal of tension during speech.
        q_score = round(
            pucker_score * WEIGHTS["pucker"]
            + brow_score * WEIGHTS["brow_down"]
            + lips_score * WEIGHTS["lips_down"]
        )

        question_results.append(
            {
                "question_id": q["question_id"],
                "pucker_score": pucker_score,
                "brow_down_score": brow_score,
                "lips_down_score": lips_score,
                "question_score": q_score,
            }
        )

    if question_results:
        overall: int | None = round(
            sum(r["question_score"] for r in question_results) / len(question_results)
        )
    else:
        # No questions means no score — None makes that explicit and prevents
        # an empty session from being indistinguishable from a perfect-zero score.
        overall = None

    return {"overall_score": overall, "question_results": question_results}
