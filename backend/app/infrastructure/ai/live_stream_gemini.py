"""Thin async wrapper around the genai Live WebSocket session.

Each instance of LiveStreamGeminiSession owns one open WS to Gemini
Live for the lifetime of one live session in our system. The
supervisor drives this object:

- send_audio_chunk(): forward 16 kHz mono PCM bytes coming from the
  browser-side audio streamer.
- iter_tool_calls(): async generator that yields every tool call the
  model emits. Each call is a small dataclass with the function name,
  the args dict, the call id (so the supervisor can ack each one) and
  the wall-clock timestamp the supervisor uses for strike ordering.
- ack_tool_call(): closes the loop by sending an empty FunctionResponse
  back. Live API 2.5 streams are designed to keep flowing after a tool
  call, but the supervisor still has to acknowledge so the model knows
  the call was consumed.
- aclose(): tear down. The connect() context manager owns the WS, so
  this object exposes both an async-context-manager protocol and an
  explicit aclose() for places (FastAPI WS handlers) where the lifetime
  is driven by an outer try/finally.

Design choices:
- We deliberately do not retry. A dropped Live WS aborts the live
  session; the user gets a clean error and can restart. Retrying inside
  the wrapper would silently hide errors that the supervisor should
  surface to the client.
- We do not transform the audio. The supervisor decides framing and
  rate; this wrapper just forwards bytes.
- The wrapper does not enforce the anti-hallucination contract. That
  logic lives in the supervisor so this file stays a thin transport.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from google import genai
from google.genai import types

from app.use_cases.live.streaming.live_prompt import build_live_streaming_prompt
from app.use_cases.live.streaming.tools import (
    LiveStreamModule,
    build_tools_for_modules,
)
from config import settings

logger = logging.getLogger(__name__)


_AUDIO_MIME = "audio/pcm;rate=16000"


@dataclass(frozen=True)
class LiveToolCall:
    """One function call yielded by the live model.

    The id is opaque; we round-trip it back through ack_tool_call so the
    model can correlate the response with the originating call.
    """

    id: str
    name: str
    args: dict
    received_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))


class LiveStreamGeminiSession:
    """Manages one open WS to Gemini Live for one live session.

    Usage from the supervisor:

        async with LiveStreamGeminiSession(modules=[...]).open() as gemini:
            asyncio.create_task(forward_chunks(gemini))
            async for call in gemini.iter_tool_calls():
                await on_tool_call(call)
                await gemini.ack_tool_call(call)

    open() returns self so the caller can use async with directly. The
    underlying genai context manager is entered there and exited on
    __aexit__ or aclose().
    """

    def __init__(self, modules: list[LiveStreamModule]):
        self._modules = modules
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._session: types.AsyncSession | None = None
        self._session_cm = None
        # Single lock so concurrent chunk-forwarders cannot interleave
        # bytes in the WS frame. Live API expects whole audio blobs, not
        # spliced fragments, so we serialize sends.
        self._send_lock = asyncio.Lock()

    def open(self) -> "_LiveOpenContext":
        return _LiveOpenContext(self)

    async def _enter(self) -> None:
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            system_instruction=build_live_streaming_prompt(self._modules),
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(**decl)
                        for decl in build_tools_for_modules(self._modules)
                    ]
                )
            ],
            # Temperature 0.3 keeps the model conservative when deciding
            # whether to fire a tool. We want false negatives over false
            # positives in a teaching tool where every cut interrupts the
            # student.
            temperature=0.3,
        )
        self._session_cm = self._client.aio.live.connect(
            model=settings.gemini_live_model,
            config=config,
        )
        self._session = await self._session_cm.__aenter__()
        logger.info(
            "Live Gemini WS opened (model=%s, modules=%s)",
            settings.gemini_live_model,
            self._modules,
        )

    async def aclose(self) -> None:
        if self._session_cm is None:
            return
        try:
            await self._session_cm.__aexit__(None, None, None)
        except Exception as exc:
            logger.warning("Error closing Live Gemini WS: %s", exc)
        finally:
            self._session = None
            self._session_cm = None

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Forward a raw 16 kHz mono PCM chunk to the live model.

        Empty chunks are ignored so the supervisor can pass through any
        slack from the upstream audio streamer without us tripping over
        the wire format.
        """

        if not pcm_bytes:
            return
        session = self._require_session()
        async with self._send_lock:
            await session.send_realtime_input(
                audio=types.Blob(data=pcm_bytes, mime_type=_AUDIO_MIME),
            )

    async def signal_audio_end(self) -> None:
        """Tell the model the user stopped sending audio for now.

        This nudges the model to flush any pending evaluation and stop
        waiting for the next chunk. The supervisor calls this on
        graceful close before aclose().
        """

        if self._session is None:
            return
        async with self._send_lock:
            await self._session.send_realtime_input(audio_stream_end=True)

    async def iter_tool_calls(self) -> AsyncIterator[LiveToolCall]:
        """Yield every function call the model emits.

        Other server messages (text deltas, generation complete, etc.)
        are ignored on purpose. response_modalities is TEXT and the
        system prompt asks for silence; if the model leaks text we
        drop it rather than surfacing noise to the supervisor.
        """

        session = self._require_session()
        async for message in session.receive():
            tool_call = getattr(message, "tool_call", None)
            if not tool_call:
                continue
            function_calls = getattr(tool_call, "function_calls", None) or []
            for fc in function_calls:
                args = dict(fc.args) if fc.args else {}
                yield LiveToolCall(id=fc.id or "", name=fc.name or "", args=args)

    async def ack_tool_call(self, call: LiveToolCall) -> None:
        """Send an empty FunctionResponse so the model can advance.

        Live 2.5 tool calling is one-way from our point of view (we do
        not need to return data), but the model still expects a
        FunctionResponse to mark the call as handled.
        """

        session = self._require_session()
        async with self._send_lock:
            await session.send_tool_response(
                function_responses=types.FunctionResponse(
                    id=call.id,
                    name=call.name,
                    response={"ok": True},
                )
            )

    def _require_session(self) -> types.AsyncSession:
        if self._session is None:
            raise RuntimeError("LiveStreamGeminiSession is not open")
        return self._session


class _LiveOpenContext:
    """Async context manager that opens and closes the wrapped session.

    Kept as a small helper class instead of using contextlib so the
    supervisor can reason about the lifecycle in terms of a typed
    object rather than an opaque async generator.
    """

    def __init__(self, owner: LiveStreamGeminiSession):
        self._owner = owner

    async def __aenter__(self) -> LiveStreamGeminiSession:
        await self._owner._enter()
        return self._owner

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._owner.aclose()
