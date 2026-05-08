from datetime import datetime, timedelta, timezone

from app.use_cases.fluency.prompt_builder import build_fluency_prompt
from app.use_cases.fluency.session_manager import FluencySessionState


def test_fluency_prompt_includes_user_prompt():
    prompt = build_fluency_prompt("Cuenta una experiencia presentando.")
    assert "Cuenta una experiencia presentando." in prompt
    assert "trabas" in prompt
    assert "repeticiones" in prompt
    assert "concordancia" in prompt
    assert "audio_intelligible" in prompt


def test_fluency_state_warns_on_low_score():
    state = FluencySessionState(user_id="u", prompt_text="p")
    should_warn, reason = state.evaluate_attention({
        "score": 62,
        "stuck_events": [],
        "repetitions": 0,
        "restarts": 0,
        "long_blocks": 0,
        "prompt_alignment_score": 90,
        "audio_intelligible": True,
    })
    assert should_warn
    assert reason == "low_fluency_score"


def test_fluency_state_warns_on_accumulated_events_in_analysis():
    state = FluencySessionState(user_id="u", prompt_text="p")
    should_warn, reason = state.evaluate_attention({
        "score": 82,
        "stuck_events": [{"word": "pero", "count": 3, "ctx": "pero pero"}],
        "repetitions": 1,
        "restarts": 1,
        "long_blocks": 0,
        "prompt_alignment_score": 90,
        "audio_intelligible": True,
    })
    assert should_warn
    assert reason == "fluency_blocks_detected"


def test_fluency_state_average_score():
    state = FluencySessionState(user_id="u", prompt_text="p")
    state.evaluate_attention({"score": 80})
    state.evaluate_attention({"score": 90})
    assert state.average_score() == 85


def test_fluency_state_warns_when_not_aligned_with_prompt():
    state = FluencySessionState(user_id="u", prompt_text="p")
    should_warn, reason = state.evaluate_attention({
        "score": 82,
        "stuck_events": [],
        "repetitions": 0,
        "restarts": 0,
        "long_blocks": 0,
        "prompt_alignment_score": 35,
        "audio_intelligible": True,
    })
    assert should_warn
    assert reason == "not_aligned_with_prompt"


def test_fluency_state_warns_when_audio_not_intelligible():
    state = FluencySessionState(user_id="u", prompt_text="p")
    should_warn, reason = state.evaluate_attention({
        "score": 0,
        "stuck_events": [],
        "repetitions": 0,
        "restarts": 0,
        "long_blocks": 0,
        "prompt_alignment_score": 0,
        "audio_intelligible": False,
    })
    assert should_warn
    assert reason == "audio_not_intelligible"


def test_fluency_state_time_limit():
    state = FluencySessionState(user_id="u", prompt_text="p")
    state.started_at = datetime.now(timezone.utc) - timedelta(seconds=190)
    should_warn, reason = state.evaluate_attention({"score": 90})
    assert should_warn
    assert reason == "time_limit"
