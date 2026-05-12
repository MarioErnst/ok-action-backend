import json
import logging

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

_STUCK_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "word": {"type": "string"},
        "count": {"type": "integer"},
        "ctx": {"type": "string"},
    },
    "required": ["word", "count", "ctx"],
}

_FLUENCY_SCHEMA = {
    "type": "object",
    "properties": {
        "audio_intelligible": {"type": "boolean"},
        "score": {"type": "integer"},
        "fluency_score": {"type": "integer"},
        "continuity_score": {"type": "integer"},
        "rhythm_score": {"type": "integer"},
        "prompt_alignment_score": {"type": "integer"},
        "coherence_score": {"type": "integer"},
        "classification": {"type": "string"},
        "stuck_events": {"type": "array", "items": _STUCK_EVENT_SCHEMA},
        "repetitions": {"type": "integer"},
        "restarts": {"type": "integer"},
        "long_blocks": {"type": "integer"},
        "wpm": {"type": "integer"},
        "pace_feedback": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "improvement_areas": {"type": "array", "items": {"type": "string"}},
        "fb": {"type": "string"},
    },
    "required": [
        "audio_intelligible",
        "score",
        "fluency_score",
        "continuity_score",
        "rhythm_score",
        "prompt_alignment_score",
        "coherence_score",
        "classification",
        "stuck_events",
        "repetitions",
        "restarts",
        "long_blocks",
        "wpm",
        "pace_feedback",
        "strengths",
        "improvement_areas",
        "fb",
    ],
}

_MIN_AUDIO_BYTES = 6400


async def analyze_fluency_audio_segment(audio_bytes: bytes, prompt: str) -> dict | None:
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
                response_schema=_FLUENCY_SCHEMA,
            ),
        )
    except Exception as exc:
        logger.error("Gemini fluency generate_content failed: %s", exc)
        return None

    if not response.text:
        return None

    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        logger.warning("JSON decode error from Gemini fluency: %s | raw: %.200s", exc, response.text)
        return None
