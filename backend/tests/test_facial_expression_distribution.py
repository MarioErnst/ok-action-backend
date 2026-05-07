from app.use_cases.facial_expression.distribution import compute_distribution


def test_no_events_returns_empty():
    dist, dom, pct = compute_distribution(10000, [])
    assert dist == {}
    assert dom is None
    assert pct is None


def test_zero_duration_returns_empty():
    dist, dom, pct = compute_distribution(0, [{"t_ms": 0, "emotion": "happy"}])
    assert dist == {}
    assert dom is None
    assert pct is None


def test_single_event_takes_full_duration():
    dist, dom, pct = compute_distribution(
        10000, [{"t_ms": 0, "emotion": "happy"}]
    )
    assert dist == {"happy": 100}
    assert dom == "happy"
    assert pct == 100


def test_two_events_split_duration():
    # happy from 0 to 4000 (40%), neutral from 4000 to 10000 (60%)
    dist, dom, pct = compute_distribution(
        10000,
        [
            {"t_ms": 0, "emotion": "happy"},
            {"t_ms": 4000, "emotion": "neutral"},
        ],
    )
    assert dist == {"happy": 40, "neutral": 60}
    assert dom == "neutral"
    assert pct == 60


def test_percentages_always_sum_to_100():
    # Three thirds — naive rounding would produce 33+33+33=99.
    dist, _, _ = compute_distribution(
        9000,
        [
            {"t_ms": 0, "emotion": "happy"},
            {"t_ms": 3000, "emotion": "sad"},
            {"t_ms": 6000, "emotion": "neutral"},
        ],
    )
    assert sum(dist.values()) == 100


def test_aggregates_repeats_of_same_emotion():
    # happy appears twice — both segments must accumulate.
    dist, dom, _ = compute_distribution(
        10000,
        [
            {"t_ms": 0, "emotion": "happy"},
            {"t_ms": 2000, "emotion": "neutral"},
            {"t_ms": 4000, "emotion": "happy"},
        ],
    )
    # happy: 0–2000 + 4000–10000 = 8000 (80%); neutral: 2000–4000 = 2000 (20%)
    assert dist == {"happy": 80, "neutral": 20}
    assert dom == "happy"


def test_unsorted_events_are_sorted_by_t():
    dist, _, _ = compute_distribution(
        10000,
        [
            {"t_ms": 5000, "emotion": "sad"},
            {"t_ms": 0, "emotion": "happy"},
        ],
    )
    assert dist == {"happy": 50, "sad": 50}
