# Tests for LiveSessionState in app.use_cases.live_session.session_manager
from app.use_cases.live_session.session_manager import LiveSessionState
from datetime import datetime, timezone, timedelta


def _make_analysis(pron_sc=90, acc_sc=90, mul_sc=90, errors=0):
    return {
        "dims": {
            "pron": {"sc": pron_sc, "err": [{"ph": "r", "w": "perro", "fix": "vibra"}] * errors},
            "acc": {"sc": acc_sc, "err": []},
            "mul": {"sc": mul_sc, "det": []},
        },
        "overall": pron_sc,
        "fb": "Bien",
    }


def test_no_stop_when_all_scores_above_threshold():
    state = LiveSessionState(user_id="u", selected_dims=["pron", "acc", "mul"])
    analysis = _make_analysis(pron_sc=80, acc_sc=85, mul_sc=90)
    should_stop, reason, dim = state.evaluate_thresholds(analysis)
    assert not should_stop


def test_stops_when_score_below_70():
    state = LiveSessionState(user_id="u", selected_dims=["pron", "acc"])
    analysis = _make_analysis(pron_sc=65)
    should_stop, reason, dim = state.evaluate_thresholds(analysis)
    assert should_stop
    assert reason == "low_score"
    assert dim == "pron"


def test_stops_when_accumulated_errors_reach_3():
    state = LiveSessionState(user_id="u", selected_dims=["pron"])
    state.evaluate_thresholds(_make_analysis(errors=2))
    should_stop, reason, dim = state.evaluate_thresholds(_make_analysis(errors=1))
    assert should_stop
    assert reason == "error_threshold"


def test_only_evaluates_selected_dims():
    state = LiveSessionState(user_id="u", selected_dims=["mul"])
    analysis = _make_analysis(pron_sc=30, mul_sc=85)
    should_stop, _, _ = state.evaluate_thresholds(analysis)
    assert not should_stop


def test_analyses_are_accumulated():
    state = LiveSessionState(user_id="u", selected_dims=["pron"])
    state.evaluate_thresholds(_make_analysis())
    state.evaluate_thresholds(_make_analysis())
    assert len(state.analyses) == 2


def test_stops_when_time_limit_reached():
    state = LiveSessionState(user_id="u", selected_dims=["pron"])
    # Backdate started_at so elapsed_seconds() returns > MAX_DURATION_SEC
    state.started_at = datetime.now(timezone.utc) - timedelta(seconds=310)
    analysis = _make_analysis(pron_sc=90)
    should_stop, reason, dim = state.evaluate_thresholds(analysis)
    assert should_stop
    assert reason == "time_limit"
