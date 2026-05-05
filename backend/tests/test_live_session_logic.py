import pytest
from app.use_cases.live_session.prompt_builder import build_system_prompt


def test_prompt_includes_only_selected_dims():
    prompt = build_system_prompt(["pron"])
    assert "pronunciacion" in prompt.lower()
    assert "acentuacion" not in prompt.lower()
    assert "muletillas" not in prompt.lower()


def test_prompt_includes_all_dims_when_all_selected():
    prompt = build_system_prompt(["pron", "acc", "mul"])
    assert "pronunciacion" in prompt.lower()
    assert "acentuacion" in prompt.lower()
    assert "muletillas" in prompt.lower()


def test_prompt_includes_eval_format_instruction():
    prompt = build_system_prompt(["pron"])
    assert "[EVAL]" in prompt
    assert "[/EVAL]" in prompt


def test_prompt_excludes_acc_key_when_not_selected():
    prompt = build_system_prompt(["pron", "mul"])
    # The response format section should not include "acc" key
    assert '"acc"' not in prompt


from app.use_cases.live_session.session_manager import LiveSessionState


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
    state = LiveSessionState(session_id="x", user_id="u", selected_dims=["pron", "acc", "mul"])
    analysis = _make_analysis(pron_sc=80, acc_sc=85, mul_sc=90)
    should_stop, reason, dim = state.evaluate_thresholds(analysis)
    assert not should_stop


def test_stops_when_score_below_70():
    state = LiveSessionState(session_id="x", user_id="u", selected_dims=["pron", "acc"])
    analysis = _make_analysis(pron_sc=65)
    should_stop, reason, dim = state.evaluate_thresholds(analysis)
    assert should_stop
    assert reason == "low_score"
    assert dim == "pron"


def test_stops_when_accumulated_errors_reach_3():
    state = LiveSessionState(session_id="x", user_id="u", selected_dims=["pron"])
    # First cycle: 2 errors (no stop yet)
    state.evaluate_thresholds(_make_analysis(errors=2))
    # Second cycle: 1 more error (total 3 -> stop)
    should_stop, reason, dim = state.evaluate_thresholds(_make_analysis(errors=1))
    assert should_stop
    assert reason == "error_threshold"


def test_only_evaluates_selected_dims():
    state = LiveSessionState(session_id="x", user_id="u", selected_dims=["mul"])
    # pron score is 30, but pron is not selected -- should not trigger
    analysis = _make_analysis(pron_sc=30, mul_sc=85)
    should_stop, _, _ = state.evaluate_thresholds(analysis)
    assert not should_stop


def test_analyses_are_accumulated():
    state = LiveSessionState(session_id="x", user_id="u", selected_dims=["pron"])
    state.evaluate_thresholds(_make_analysis())
    state.evaluate_thresholds(_make_analysis())
    assert len(state.analyses) == 2
