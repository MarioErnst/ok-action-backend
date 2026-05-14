"""Single Gemini call that evaluates an audio against several modules at once.

Live session sends one audio blob (recorded via MediaRecorder) and a list
of selected modules. We build a composed prompt and JSON schema from
app.use_cases.live.composed and ask Gemini to produce a single response
covering every selected module. The caller is responsible for parsing
that response and persisting children sessions.

The mime_type is whatever MediaRecorder produced on the client (typically
audio/webm on Chrome/Android and audio/mp4 on iOS Safari). Gemini accepts
both. We do not enforce a minimum byte size here: the prompt's audio gate
asks Gemini to set audio_intelligible=false for empty or unintelligible
input, which is more reliable than guessing a byte threshold across
codecs with very different bitrates.
"""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from app.use_cases.live.composed.prompts import (
    ComposableModule,
    build_composed_prompt,
)
from app.use_cases.live.composed.schemas import build_composed_schema
from config import settings

logger = logging.getLogger(__name__)


_MODEL = "gemini-2.5-flash"


async def evaluate_composed_audio(
    audio_bytes: bytes,
    mime_type: str,
    modules: list[ComposableModule],
    prompt_text: str | None = None,
) -> dict | None:
    """Send the audio plus a composed prompt to Gemini and return the parsed dict.

    Returns None on Gemini failure or unparseable response. The orchestrator
    treats None as "no evaluation produced", not as an error to surface to
    the user — the live session itself remains valid even if the audio could
    not be evaluated; we just do not persist children for this audio.
    """

    composed_prompt = build_composed_prompt(modules, prompt_text=prompt_text)
    composed_schema = build_composed_schema(modules)

    client = genai.Client(api_key=settings.gemini_api_key)
    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    text_part = types.Part.from_text(text=composed_prompt)

    try:
        response = await client.aio.models.generate_content(
            model=_MODEL,
            contents=[types.Content(role="user", parts=[audio_part, text_part])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=composed_schema,
                # Lowered from the Gemini default (1.0) so detection-heavy
                # outputs (muletillas list, phoneme errors, prosodic errors)
                # become near-deterministic. 0.2 leaves enough variance for
                # the natural-language feedback strings without inviting
                # the hallucinated false positives we observed at default.
                temperature=0.2,
            ),
        )
    except Exception as exc:
        logger.error("Composed live Gemini call failed: %s", exc)
        return None

    if not response.text:
        logger.warning("Composed live Gemini returned empty response")
        return None

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Composed live Gemini JSON decode error: %s | raw: %.300s",
            exc,
            response.text,
        )
        return None

    # TEMPORARY DEBUG LOG — remove once live grounding hotfix is validated.
    # Uses print(flush=True) instead of logger.info because uvicorn's
    # default --log-level only configures its own loggers; app-level info
    # logs are silently dropped unless logging is configured globally.
    # print() guarantees the diagnostic shows up in stdout.
    print(
        f"[DEBUG_LIVE_COMPOSED] modules={modules} "
        f"response={json.dumps(parsed, ensure_ascii=False)[:4000]}",
        flush=True,
    )
    return parsed
