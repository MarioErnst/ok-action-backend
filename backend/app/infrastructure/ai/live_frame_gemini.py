"""Per-frame Gemini call for live session strike detection.

This client mirrors composed_live_gemini.py but is tuned for frames:
- Audio + structured-output Gemini Flash calls run in the 3-15 s range
  in practice (cold start + decode + thinking + JSON schema generation).
  We default to a 20 s timeout to absorb cold-start latency on the
  first frames of a session. If a call still misses the deadline we
  log + return None so the strike pipeline can drop the frame and
  move on rather than blocking the chain.
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
_DEFAULT_TIMEOUT_S = 20.0


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
                    # Bumped from 0.2 to 0.4 because the previous setting,
                    # combined with strict anti-hallucination wording in
                    # the prompt, made Gemini return empty phoneme_errors
                    # and prosodic_errors even when the user repeatedly
                    # mispronounced. 0.4 keeps the response largely stable
                    # while giving the model room to flag perceptible
                    # errors that it would otherwise suppress.
                    temperature=0.4,
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
