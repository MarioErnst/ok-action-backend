# Wraps Gemini Live API session. Full docs: documentacion/modulos/sesion-libre.md
import re
import json
import logging

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

EVAL_PATTERN = re.compile(r'\[EVAL\](.*?)\[/EVAL\]', re.DOTALL)


class GeminiLiveError(Exception):
    """Raised when the Gemini Live API connection or session fails."""


def parse_eval_block(raw_text: str) -> dict | None:
    """
    Extracts and parses the [EVAL]...[/EVAL] JSON block from model output.
    Returns None if the block is missing or malformed.
    """
    match = EVAL_PATTERN.search(raw_text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


class GeminiLiveService:
    """
    Manages a single Gemini Live API session for real-time speech analysis.
    VAD is disabled; the caller controls turn boundaries via trigger_analysis().

    Usage:
        async with GeminiLiveService(system_prompt) as svc:
            await svc.send_audio_chunk(pcm_bytes)
            await svc.trigger_analysis()
            result = await svc.receive_analysis()
    """

    def __init__(self, system_prompt: str) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._system_prompt = system_prompt
        self._session = None
        self._context = None

    async def __aenter__(self) -> "GeminiLiveService":
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            system_instruction=types.Content(
                parts=[types.Part(text=self._system_prompt)],
            ),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=True
                )
            ),
        )
        try:
            self._context = self._client.aio.live.connect(
                model="gemini-3.1-flash-live-preview",
                config=config,
            )
            self._session = await self._context.__aenter__()
        except Exception as exc:
            raise GeminiLiveError(f"Failed to open Gemini Live session: {exc}") from exc
        return self

    async def __aexit__(self, *args) -> None:
        if self._context:
            await self._context.__aexit__(*args)
        self._session = None
        self._context = None

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Forwards a raw PCM 16-bit 16kHz chunk to Gemini."""
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
        )

    async def trigger_analysis(self) -> None:
        """Signals end of current audio segment to trigger model response."""
        await self._session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="")]),
            turn_complete=True,
        )

    async def receive_analysis(self) -> dict | None:
        """
        Accumulates response tokens until turn_complete, then parses the [EVAL] block.
        Returns parsed dict or None if parsing fails or the session errors.
        """
        buffer = ""
        try:
            async for response in self._session.receive():
                if response.text:
                    buffer += response.text
                if (
                    response.server_content
                    and response.server_content.turn_complete
                ):
                    break
        except Exception as exc:
            logger.warning("Error receiving from Gemini Live: %s", exc)
            return None

        if not buffer:
            return None

        result = parse_eval_block(buffer)
        if result is None:
            logger.warning("Could not parse EVAL block from: %.200s", buffer)
        return result
