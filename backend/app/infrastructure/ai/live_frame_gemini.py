"""Per-frame Gemini call for live session strike detection.

This client mirrors composed_live_gemini.py but is tuned for frames:
- Shorter timeout (5 s by default vs the composed default) — if a frame
  is slower than that the client side is better off dropping it than
  holding up the strike pipeline.
- No retry. Losing a single frame is acceptable; the next one will be
  ready in 5 to 8 seconds and the strike counter is tolerant.
- Same fixed model id (no *_latest aliases).
"""

from __future__ import annotations

import asyncio
import json
import logging

from google import genai
from google.genai import types

from app.use_cases.live.streaming.prompts import (
    FrameModule,
    build_frame_prompt,
)
from app.use_cases.live.streaming.schemas import build_frame_schema
from config import settings

logger = logging.getLogger(__name__)


_MODEL = "gemini-2.5-flash"
_DEFAULT_TIMEOUT_S = 5.0


async def evaluate_frame_audio(
    audio_bytes: bytes,
    mime_type: str,
    modules: list[FrameModule],
    evaluated_so_far_seconds: int | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> dict | None:
    """Send a single audio frame to Gemini and return the parsed dict.

    Returns None when:
      * Gemini errored or timed out.
      * The response was empty.
      * The response could not be JSON-decoded.
    The caller treats None as "skip this frame" — never as a hard error
    on the live session.
    """

    frame_prompt = build_frame_prompt(modules, evaluated_so_far_seconds)
    frame_schema = build_frame_schema(modules)

    client = genai.Client(api_key=settings.gemini_api_key)
    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    text_part = types.Part.from_text(text=frame_prompt)

    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=_MODEL,
                contents=[types.Content(role="user", parts=[audio_part, text_part])],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=frame_schema,
                ),
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        logger.warning("Frame Gemini call timed out after %.1fs", timeout_s)
        return None
    except Exception as exc:
        logger.error("Frame Gemini call failed: %s", exc)
        return None

    if not response.text:
        logger.warning("Frame Gemini returned empty response")
        return None

    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Frame Gemini JSON decode error: %s | raw: %.200s",
            exc,
            response.text,
        )
        return None
