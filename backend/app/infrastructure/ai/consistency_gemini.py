import json
import logging

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

_TIMELINE_SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "segment": {"type": "string"},
        "stability": {"type": "number"},
        "rhythm": {"type": "number"},
        "volume": {"type": "number"},
        "clarity": {"type": "number"},
        "focus": {"type": "number"},
        "confidence": {"type": "number"},
        "structure": {"type": "number"},
        "note": {"type": "string"},
    },
    "required": [
        "segment",
        "stability",
        "rhythm",
        "volume",
        "clarity",
        "focus",
        "confidence",
        "structure",
        "note",
    ],
}

_VOLATILITY_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "area": {"type": "string"},
        "segment": {"type": "string"},
        "severity": {"type": "string"},
        "note": {"type": "string"},
        "suggestion": {"type": "string"},
    },
    "required": ["area", "segment", "severity", "note", "suggestion"],
}

_CONSISTENCY_SCHEMA = {
    "type": "object",
    "properties": {
        "audio_intelligible": {"type": "boolean"},
        "score": {"type": "number"},
        "rhythm_consistency_score": {"type": "number"},
        "volume_consistency_score": {"type": "number"},
        "clarity_consistency_score": {"type": "number"},
        "focus_consistency_score": {"type": "number"},
        "confidence_consistency_score": {"type": "number"},
        "structure_consistency_score": {"type": "number"},
        "classification": {"type": "string"},
        "timeline": {"type": "array", "items": _TIMELINE_SEGMENT_SCHEMA},
        "volatility_events": {"type": "array", "items": _VOLATILITY_EVENT_SCHEMA},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "improvement_areas": {"type": "array", "items": {"type": "string"}},
        "recommendation": {"type": "string"},
        "fb": {"type": "string"},
    },
    "required": [
        "audio_intelligible",
        "score",
        "rhythm_consistency_score",
        "volume_consistency_score",
        "clarity_consistency_score",
        "focus_consistency_score",
        "confidence_consistency_score",
        "structure_consistency_score",
        "classification",
        "timeline",
        "volatility_events",
        "strengths",
        "improvement_areas",
        "recommendation",
        "fb",
    ],
}

_MIN_AUDIO_BYTES = 6400


async def analyze_consistency_audio(audio_bytes: bytes, prompt: str) -> dict | None:
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
                response_schema=_CONSISTENCY_SCHEMA,
            ),
        )
    except Exception as exc:
        logger.error("Gemini consistency generate_content failed: %s", exc)
        return None

    if not response.text:
        return None

    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        logger.warning("JSON decode error from Gemini consistency: %s | raw: %.200s", exc, response.text)
        return None
