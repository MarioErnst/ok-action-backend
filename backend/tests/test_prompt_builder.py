# Tests for build_system_prompt in app.use_cases.live_session.prompt_builder
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
    assert '"acc"' not in prompt
