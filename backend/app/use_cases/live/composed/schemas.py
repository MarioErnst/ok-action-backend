"""Composed Gemini response schema builder for live audio evaluation.

Mirrors the prompt sections in prompts.py: each audio module contributes a
top-level key to the unified response schema, and only the selected modules
appear in the schema. The shape per module is intentionally smaller than the
standalone schemas: live evaluation persists only the columns that exist in
<modulo>_metrics, so we ask Gemini for those plus a feedback string per
module. Anything else (per-event timelines, phoneme-level errors) would just
be discarded.

facial_expression is a valid composable from the client's perspective but
its data does not come from Gemini's text response — it comes from the
client's emotion classifier and is submitted directly to the finalize
endpoint. The schema therefore does not include a facial_expression key.

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


_ACCENTUATION_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "pronunciation_score": {"type": "integer"},
        "rhythm_score": {"type": "integer"},
        "intonation_score": {"type": "integer"},
        "stress_score": {"type": "integer"},
        "feedback": {"type": "string"},
    },
    "required": [
        "pronunciation_score",
        "rhythm_score",
        "intonation_score",
        "stress_score",
        "feedback",
    ],
}


_PRONUNCIATION_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "vowel_score": {"type": "integer"},
        "consonant_score": {"type": "integer"},
        "fluency_score": {"type": "integer"},
        "intelligibility_score": {"type": "integer"},
        "feedback": {"type": "string"},
    },
    "required": [
        "vowel_score",
        "consonant_score",
        "fluency_score",
        "intelligibility_score",
        "feedback",
    ],
}


_SCHEMA_BY_MODULE: dict[ComposableModule, dict[str, Any]] = {
    "muletillas": _MULETILLAS_SECTION_SCHEMA,
    "accentuation": _ACCENTUATION_SECTION_SCHEMA,
    "pronunciation": _PRONUNCIATION_SECTION_SCHEMA,
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
