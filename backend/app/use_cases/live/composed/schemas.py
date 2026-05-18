"""Composed Gemini response schema builder for live audio evaluation.

Mirrors the prompt section in prompts.py: today the only module Gemini
evaluates from the audio is muletillas. facial_expression, phonation
and loudness are computed client-side and submitted alongside the
audio in the composed evaluation request; this schema therefore does
not include keys for them.

Field types are strict integers (not numbers) to avoid floats that violate
Pydantic int validation downstream — same rule we adopted in the standalone
modules.
"""

from __future__ import annotations

from typing import Any

from app.use_cases.live.composed.prompts import VALID_MODULES, ComposableModule


_MULETILLAS_DETECTED_ITEM = {
    "type": "object",
    "properties": {
        "word": {"type": "string"},
        "count": {"type": "integer"},
        "severity": {"type": "string"},
        "suggestion": {"type": "string"},
    },
    "required": ["word", "count", "severity", "suggestion"],
}


# Each occurrence anchors to the root transcript via start_char (inclusive) +
# end_char (exclusive). The prompt enforces transcript[start:end] == word so
# Gemini cannot list a muletilla that is not in its own transcription.
_MULETILLAS_POSITION_ITEM = {
    "type": "object",
    "properties": {
        "word": {"type": "string"},
        "start_char": {"type": "integer"},
        "end_char": {"type": "integer"},
    },
    "required": ["word", "start_char", "end_char"],
}


_MULETILLAS_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "fluency_score": {"type": "integer"},
        "total_muletillas": {"type": "integer"},
        "detected": {"type": "array", "items": _MULETILLAS_DETECTED_ITEM},
        "muletillas_positions": {
            "type": "array",
            "items": _MULETILLAS_POSITION_ITEM,
        },
        "feedback": {"type": "string"},
    },
    "required": [
        "fluency_score",
        "total_muletillas",
        "detected",
        "muletillas_positions",
        "feedback",
    ],
}


_SCHEMA_BY_MODULE: dict[ComposableModule, dict[str, Any]] = {
    "muletillas": _MULETILLAS_SECTION_SCHEMA,
}


def build_composed_schema(modules: list[ComposableModule]) -> dict[str, Any]:
    """Build a JSON schema for the unified Gemini response.

    Only selected audio modules appear as keys. audio_intelligible is always
    present so the orchestrator can short-circuit persistence when Gemini
    reports the audio is empty or unintelligible. The order of keys follows
    VALID_MODULES to keep schemas deterministic regardless of input ordering.

    facial_expression is filtered out at this layer because it does not
    come from Gemini.
    """

    if not modules:
        raise ValueError("At least one module must be selected for live evaluation")

    invalid = [m for m in modules if m not in VALID_MODULES]
    if invalid:
        raise ValueError(f"Invalid module(s): {invalid}")

    audio_modules: list[ComposableModule] = [
        m for m in VALID_MODULES if m in modules and m in _SCHEMA_BY_MODULE
    ]

    properties: dict[str, Any] = {"audio_intelligible": {"type": "boolean"}}
    required: list[str] = ["audio_intelligible"]

    # Transcript lives at the root because every audio module that returns
    # anchored items references the same transcription. Required as soon as
    # any audio module is selected — without it the per-module anchoring
    # contract cannot hold.
    properties["transcript"] = {"type": "string"}
    required.append("transcript")

    for module in audio_modules:
        properties[module] = _SCHEMA_BY_MODULE[module]
        required.append(module)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }
