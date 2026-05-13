"""Frame-evaluation response schema builder.

Mirrors the prompt sections in prompts.py: only requested modules appear
in the response. The schema is strict on integer types because Gemini
sometimes returns floats that crash Pydantic int validation downstream.

Differences relative to composed/schemas.py:
- No feedback strings in any section.
- evaluated_until_seconds at the root, integer (seconds, not ms,
  rounded down by Gemini per the prompt instruction).
- muletillas.detected items include timestamp_ms instead of the
  open-ended suggestion string from the composed schema.
- No audio_intelligible gate: the prompt asks Gemini to return neutral
  50s instead of failing the frame.
"""

from __future__ import annotations

from typing import Any

from app.use_cases.live.streaming.prompts import VALID_FRAME_MODULES, FrameModule


_MULETILLAS_DETECTED_ITEM = {
    "type": "object",
    "properties": {
        "word": {"type": "string"},
        "count": {"type": "integer"},
        "severity": {"type": "string"},
        "timestamp_ms": {"type": "integer"},
    },
    "required": ["word", "count", "severity", "timestamp_ms"],
}


_FRAME_MULETILLAS_SCHEMA = {
    "type": "object",
    "properties": {
        "total": {"type": "integer"},
        "detected": {"type": "array", "items": _MULETILLAS_DETECTED_ITEM},
    },
    "required": ["total", "detected"],
}


_FRAME_ACCENTUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "pronunciation_score": {"type": "integer"},
        "rhythm_score": {"type": "integer"},
        "intonation_score": {"type": "integer"},
        "stress_score": {"type": "integer"},
    },
    "required": [
        "pronunciation_score",
        "rhythm_score",
        "intonation_score",
        "stress_score",
    ],
}


_FRAME_PRONUNCIATION_SCHEMA = {
    "type": "object",
    "properties": {
        "vowel_score": {"type": "integer"},
        "consonant_score": {"type": "integer"},
        "fluency_score": {"type": "integer"},
        "intelligibility_score": {"type": "integer"},
    },
    "required": [
        "vowel_score",
        "consonant_score",
        "fluency_score",
        "intelligibility_score",
    ],
}


_SCHEMA_BY_MODULE: dict[FrameModule, dict[str, Any]] = {
    "muletillas": _FRAME_MULETILLAS_SCHEMA,
    "accentuation": _FRAME_ACCENTUATION_SCHEMA,
    "pronunciation": _FRAME_PRONUNCIATION_SCHEMA,
}


def build_frame_schema(modules: list[FrameModule]) -> dict[str, Any]:
    """Build the JSON schema for the Gemini frame response.

    evaluated_until_seconds is always required so the client can
    correlate the response with the fragment it sent (and ignore the
    portion that Gemini said it skipped).
    """

    if not modules:
        raise ValueError("At least one module must be selected for frame evaluation")

    invalid = [m for m in modules if m not in VALID_FRAME_MODULES]
    if invalid:
        raise ValueError(f"Invalid module(s): {invalid}")

    ordered_unique: list[FrameModule] = [m for m in VALID_FRAME_MODULES if m in modules]

    properties: dict[str, Any] = {
        "evaluated_until_seconds": {"type": "integer"},
    }
    required: list[str] = ["evaluated_until_seconds"]

    for module in ordered_unique:
        properties[module] = _SCHEMA_BY_MODULE[module]
        required.append(module)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }
