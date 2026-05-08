# Wraps Gemini API for live session audio analysis. Full docs: documentacion/modulos/sesion-libre.md
import json
import logging

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

_PRON_ERR_SCHEMA = {
    "type": "object",
    "properties": {
        "ph": {"type": "string"},
        "w": {"type": "string"},
        "fix": {"type": "string"},
    },
    "required": ["ph", "w", "fix"],
}

_ACC_ERR_SCHEMA = {
    "type": "object",
    "properties": {
        "w": {"type": "string"},
        "exp": {"type": "string"},
        "act": {"type": "string"},
    },
    "required": ["w", "exp", "act"],
}

_MUL_DET_SCHEMA = {
    "type": "object",
    "properties": {
        "w": {"type": "string"},
        "n": {"type": "integer"},
        # Short transcript excerpt (up to ~10 words) showing where the filler appeared
        "ctx": {"type": "string"},
    },
    "required": ["w", "n", "ctx"],
}

_PAUSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sc": {"type": "number"},
        "total_pauses": {"type": "integer"},
        "avg_pause_ms": {"type": "integer"},
        "longest_pause_ms": {"type": "integer"},
        "silence_ratio": {"type": "number"},
        "classification": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": [
        "sc",
        "total_pauses",
        "avg_pause_ms",
        "longest_pause_ms",
        "silence_ratio",
        "classification",
        "note",
    ],
}

_FLUENCY_SCHEMA = {
    "type": "object",
    "properties": {
        "sc": {"type": "number"},
        "classification": {"type": "string"},
        "wpm": {"type": "integer"},
        "repetitions": {"type": "integer"},
        "restarts": {"type": "integer"},
        "long_blocks": {"type": "integer"},
        "pace_feedback": {"type": "string"},
        "note": {"type": "string"},
        "det": {"type": "array", "items": _MUL_DET_SCHEMA},
    },
    "required": [
        "sc",
        "classification",
        "wpm",
        "repetitions",
        "restarts",
        "long_blocks",
        "pace_feedback",
        "note",
        "det",
    ],
}

_CONSISTENCY_DET_SCHEMA = {
    "type": "object",
    "properties": {
        "area": {"type": "string"},
        "severity": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["area", "severity", "note"],
}

_PRECISION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "relevance": {"type": "integer"},
        "directness": {"type": "integer"},
        "conciseness": {"type": "integer"},
        "overall": {"type": "integer"},
        "feedback": {"type": "string"},
        "audio_intelligible": {"type": "boolean"},
    },
    "required": ["relevance", "directness", "conciseness", "overall", "feedback", "audio_intelligible"],
}

_DIM_SCHEMAS: dict[str, dict] = {
    "pron": {
        "type": "object",
        "properties": {
            "sc": {"type": "number"},
            "err": {"type": "array", "items": _PRON_ERR_SCHEMA},
        },
        "required": ["sc", "err"],
    },
    "acc": {
        "type": "object",
        "properties": {
            "sc": {"type": "number"},
            "err": {"type": "array", "items": _ACC_ERR_SCHEMA},
        },
        "required": ["sc", "err"],
    },
    "mul": {
        "type": "object",
        "properties": {
            "sc": {"type": "number"},
            "det": {"type": "array", "items": _MUL_DET_SCHEMA},
        },
        "required": ["sc", "det"],
    },
    "pause": _PAUSE_SCHEMA,
    "fluency": _FLUENCY_SCHEMA,
    "consistency": {
        "type": "object",
        "properties": {
            "sc": {"type": "number"},
            "classification": {"type": "string"},
            "rhythm": {"type": "number"},
            "volume": {"type": "number"},
            "clarity": {"type": "number"},
            "focus": {"type": "number"},
            "confidence": {"type": "number"},
            "structure": {"type": "number"},
            "note": {"type": "string"},
            "det": {"type": "array", "items": _CONSISTENCY_DET_SCHEMA},
        },
        "required": [
            "sc",
            "classification",
            "rhythm",
            "volume",
            "clarity",
            "focus",
            "confidence",
            "structure",
            "note",
            "det",
        ],
    },
}

# Minimum PCM bytes to bother sending (0.2s at 16kHz / 16-bit = 6400 bytes)
_MIN_AUDIO_BYTES = 6400


def _build_response_schema(selected_dims: list[str]) -> dict:
    """Builds a JSON schema restricted to the selected dimensions."""
    dims_props = {dim: _DIM_SCHEMAS[dim] for dim in selected_dims if dim in _DIM_SCHEMAS}
    top_props: dict = {
        "dims": {
            "type": "object",
            "properties": dims_props,
            "required": list(dims_props.keys()),
        },
        "overall": {"type": "number"},
        "fb": {"type": "string"},
    }
    required = ["dims", "overall", "fb"]
    if "precision" in selected_dims:
        top_props["precision"] = _PRECISION_SCHEMA
        required.append("precision")
    return {
        "type": "object",
        "properties": top_props,
        "required": required,
    }


async def analyze_audio_segment(
    audio_bytes: bytes,
    selected_dims: list[str],
    prompt: str,
) -> dict | None:
    """
    Sends a buffered PCM 16-bit 16kHz audio segment to Gemini for speech analysis.
    Returns the parsed analysis dict or None if the segment is too short or the call fails.

    Args:
        audio_bytes: Raw PCM bytes (16-bit, 16kHz, mono).
        selected_dims: Dimensions to evaluate.
        prompt: System prompt built by prompt_builder.build_system_prompt().
    """
    if len(audio_bytes) < _MIN_AUDIO_BYTES:
        return None

    client = genai.Client(api_key=settings.gemini_api_key)
    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/pcm;rate=16000")
    text_part = types.Part.from_text(text=prompt)

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(role="user", parts=[audio_part, text_part])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_build_response_schema(selected_dims),
            ),
        )
    except Exception as exc:
        logger.error("Gemini generate_content failed: %s", exc)
        return None

    raw_text = response.text
    if not raw_text:
        logger.warning("Empty response from Gemini for audio segment")
        return None

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning("JSON decode error from Gemini: %s | raw: %.200s", exc, raw_text)
        return None
