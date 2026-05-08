from app.use_cases.consistency.prompt_builder import build_consistency_prompt
from app.use_cases.consistency.session_manager import (
    ConsistencySessionState,
    build_no_audio_analysis,
)


def test_consistency_prompt_includes_user_prompt_and_core_dimensions():
    prompt = build_consistency_prompt("Presenta una propuesta de mejora para tu equipo.")

    assert "Presenta una propuesta de mejora para tu equipo." in prompt
    assert "inicio" in prompt
    assert "medio" in prompt
    assert "cierre" in prompt
    assert "audio_intelligible" in prompt
    assert "focus_consistency_score" in prompt


def test_consistency_no_audio_analysis_is_not_evaluable():
    analysis = build_no_audio_analysis()

    assert analysis["audio_intelligible"] is False
    assert analysis["score"] == 0
    assert analysis["classification"] == "not_evaluable"
    assert analysis["timeline"] == []


def test_consistency_state_warns_on_low_score():
    state = ConsistencySessionState(user_id="u", prompt_text="p")
    state.set_analysis({
        "audio_intelligible": True,
        "score": 62,
        "volatility_events": [],
    })

    assert state.warning_reason() == "low_consistency_score"
    assert state.final_score() == 62


def test_consistency_state_warns_on_volatility_events():
    state = ConsistencySessionState(user_id="u", prompt_text="p")
    state.set_analysis({
        "audio_intelligible": True,
        "score": 82,
        "volatility_events": [
            {"area": "ritmo", "segment": "medio", "severity": "media", "note": "Cambio brusco"},
            {"area": "volumen", "segment": "cierre", "severity": "media", "note": "Baja intensidad"},
            {"area": "foco", "segment": "cierre", "severity": "alta", "note": "Pierde la idea central"},
        ],
    })

    assert state.warning_reason() == "consistency_breaks_detected"


def test_consistency_state_warns_when_audio_not_intelligible():
    state = ConsistencySessionState(user_id="u", prompt_text="p")
    state.set_analysis({
        "audio_intelligible": False,
        "score": 0,
        "volatility_events": [],
    })

    assert state.warning_reason() == "audio_not_intelligible"
