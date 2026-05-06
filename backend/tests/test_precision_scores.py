from app.use_cases.precision.evaluate_precision_response import calculate_overall_score


def test_overall_score_formula():
    # (40 * 0.4) + (30 * 0.3) + (30 * 0.3) = 16 + 9 + 9 = 34
    assert calculate_overall_score(relevance=40, directness=30, conciseness=30) == 34


def test_overall_score_rounds_to_int():
    # (75 * 0.4) + (80 * 0.3) + (85 * 0.3) = 30 + 24 + 25.5 = 79.5 → 80
    result = calculate_overall_score(relevance=75, directness=80, conciseness=85)
    assert isinstance(result, int)
    assert result == 80


def test_overall_score_perfect():
    assert calculate_overall_score(100, 100, 100) == 100
