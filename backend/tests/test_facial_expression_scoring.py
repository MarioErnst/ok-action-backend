from app.use_cases.facial_expression.analyze_session import (
    score_expression,
    calculate_session_scores,
)


def test_score_expression_perfect():
    # All frames well below threshold — score must be 100
    baseline = 0.05
    frames = [{"pk": 0.06, "bd": 0.07, "ld": 0.04}] * 30
    result = score_expression(frames, baseline, threshold=0.15, key="pk")
    assert result == 100


def test_score_expression_half_bad():
    baseline = 0.05
    good = {"pk": 0.10}  # deviation 0.05 — below 0.15 threshold
    bad = {"pk": 0.25}   # deviation 0.20 — above 0.15 threshold
    frames = [good] * 15 + [bad] * 15
    result = score_expression(frames, baseline, threshold=0.15, key="pk")
    assert result == 50


def test_score_expression_empty_frames():
    result = score_expression([], 0.05, threshold=0.15, key="pk")
    assert result == 100


def test_calculate_session_scores_structure():
    baseline = {"pucker": 0.05, "brow_down": 0.08, "lips_down": 0.04}
    questions = [
        {
            "question_id": "q1",
            "frames": [{"pk": 0.06, "bd": 0.09, "ld": 0.05}] * 20,
        }
    ]
    result = calculate_session_scores(baseline, questions)
    assert "overall_score" in result
    assert "question_results" in result
    assert len(result["question_results"]) == 1
    qr = result["question_results"][0]
    assert qr["question_id"] == "q1"
    assert "pucker_score" in qr
    assert "brow_down_score" in qr
    assert "lips_down_score" in qr
    assert "question_score" in qr
    assert 0 <= result["overall_score"] <= 100


def test_calculate_session_scores_all_perfect():
    baseline = {"pucker": 0.05, "brow_down": 0.08, "lips_down": 0.04}
    questions = [
        {"question_id": "q1", "frames": [{"pk": 0.06, "bd": 0.09, "ld": 0.05}] * 20},
        {"question_id": "q2", "frames": [{"pk": 0.07, "bd": 0.08, "ld": 0.04}] * 20},
    ]
    result = calculate_session_scores(baseline, questions)
    assert result["overall_score"] == 100
