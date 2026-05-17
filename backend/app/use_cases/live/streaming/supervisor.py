"""Per-session orchestrator that bridges the browser WS to Gemini Live.

One supervisor instance lives for the duration of one live session. It
owns three concerns and nothing else:

1. Forward inbound audio chunks (from the client WS) into the Gemini
   live session.
2. Pull tool calls from the Gemini live session, filter them through
   the anti-hallucination contract, and emit a strike event back to
   the client WS for every valid call.
3. Persist nothing. The composed-eval endpoint is still the single
   source of truth for child sessions in the database; the supervisor
   only orchestrates real-time signals.

The strike threshold (1 strike = cut) lives on the frontend so the
backend stays stateless on the rules: it emits one event per valid
tool call, the client decides when to stop. That mirrors how the old
frame pipeline worked and keeps the cut policy editable without a
backend deploy.

Composition with the existing pipeline:
- start_live_session creates the parent row in BD; the supervisor
  attaches to it via session_id and never writes to BD.
- The client opens the WS once start() succeeds; the supervisor
  authenticates via the FastAPI dependency before instantiating.
- On client disconnect, the supervisor closes the Gemini WS and
  returns. The router handler runs no extra cleanup.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.infrastructure.ai.live_stream_gemini import (
    LiveStreamGeminiSession,
    LiveToolCall,
)
from app.use_cases.live.streaming.tools import (
    TOOL_NAME_TO_MODULE,
    LiveStreamModule,
)


logger = logging.getLogger(__name__)


# Snippets shorter than this are considered no-evidence and dropped.
# Tuned so the model has to actually echo back at least a couple of
# words; one-word "snippets" usually mean the model invented the call.
_MIN_SNIPPET_CHARS = 4


# Valid severities the supervisor surfaces. Anything else gets defaulted
# to 'low' so a malformed args dict never bypasses the filter chain.
_VALID_SEVERITIES = frozenset({"low", "medium", "high"})


@dataclass(frozen=True)
class StrikeEvent:
    """Strike event that the supervisor emits towards the client.

    category is the user-facing module name (matches the LiveStreamModule
    enum and the frontend's domain). word/snippet/severity travel with
    the event so the UI can render an immediate, specific hint instead
    of a generic "corten".
    """

    category: LiveStreamModule
    word: str
    transcript_snippet: str
    severity: str
    received_at_ms: int


# Callback signature for delivering a strike to the client transport.
# Async so the router can await its own WS send. The supervisor never
# touches the underlying transport directly; tests can pass a fake.
StrikeSink = Callable[[StrikeEvent], Awaitable[None]]


class LiveStreamSupervisor:
    """Orchestrates one live streaming session."""

    def __init__(
        self,
        modules: list[LiveStreamModule],
        strike_sink: StrikeSink,
    ):
        if not modules:
            raise ValueError("supervisor requires at least one module")
        self._modules = modules
        self._strike_sink = strike_sink
        self._gemini: LiveStreamGeminiSession | None = None
        self._receive_task: asyncio.Task | None = None

    async def run(self, audio_iter) -> None:
        """Drive the session until either audio_iter ends or Gemini dies.

        audio_iter is an async iterator of raw PCM byte chunks coming
        from the browser. We spawn a parallel task that listens to
        Gemini and then sequentially forward audio until the client
        stops sending. Returning from this method tears down both ends.

        Errors propagate. The router wraps run() in a try/except so the
        client WS gets a clean close frame on failure.
        """

        logger.info(
            "[supervisor] starting (modules=%s)", self._modules,
        )
        gemini = LiveStreamGeminiSession(modules=self._modules)
        async with gemini.open() as g:
            self._gemini = g
            self._receive_task = asyncio.create_task(self._receive_loop(g))
            chunks_received = 0
            bytes_received = 0
            try:
                async for chunk in audio_iter:
                    if not chunk:
                        continue
                    chunks_received += 1
                    bytes_received += len(chunk)
                    if chunks_received in (1, 10, 100, 1000) or chunks_received % 500 == 0:
                        logger.info(
                            "[supervisor] forwarded %d chunks / %d bytes from client",
                            chunks_received,
                            bytes_received,
                        )
                    await g.send_audio_chunk(chunk)
                logger.info(
                    "[supervisor] audio iterator drained after %d chunks / %d bytes, signaling end",
                    chunks_received,
                    bytes_received,
                )
                # Tell the model the user stopped pushing audio so it
                # flushes any pending evaluation before we tear down.
                await g.signal_audio_end()
            finally:
                if self._receive_task and not self._receive_task.done():
                    self._receive_task.cancel()
                    try:
                        await self._receive_task
                    except asyncio.CancelledError:
                        pass
                self._receive_task = None
                self._gemini = None
                logger.info("[supervisor] finished")

    async def _receive_loop(self, gemini: LiveStreamGeminiSession) -> None:
        """Pull tool calls from Gemini and forward valid strikes."""

        logger.info("[supervisor] receive loop started")
        try:
            await self._consume_tool_calls(gemini)
        finally:
            logger.info("[supervisor] receive loop ended")

    async def _consume_tool_calls(self, gemini: LiveStreamGeminiSession) -> None:
        async for call in gemini.iter_tool_calls():
            try:
                event = self._normalize_call(call)
            except Exception as exc:
                logger.warning(
                    "[supervisor] dropping malformed tool call (%s): %s",
                    call.name,
                    exc,
                )
                # Still ack so the model does not retry.
                await gemini.ack_tool_call(call)
                continue

            if event is None:
                # Anti-hallucination filter rejected the call. Ack but
                # do not emit a strike.
                await gemini.ack_tool_call(call)
                continue

            logger.info(
                "[supervisor] STRIKE category=%s word=%r severity=%s snippet=%r received_at_ms=%d",
                event.category,
                event.word,
                event.severity,
                event.transcript_snippet,
                event.received_at_ms,
            )
            try:
                await self._strike_sink(event)
            except Exception as exc:
                logger.warning("[supervisor] strike sink raised: %s", exc)
            finally:
                await gemini.ack_tool_call(call)

    def _normalize_call(self, call: LiveToolCall) -> StrikeEvent | None:
        """Translate a raw tool call into a StrikeEvent or drop it.

        Drops the call when:
        - the tool name is not one of the three known names
        - transcript_snippet is missing, empty, or below the minimum
          length threshold
        - word is missing or empty
        """

        category = TOOL_NAME_TO_MODULE.get(call.name)
        if category is None:
            logger.warning("[supervisor] unknown tool name from Gemini: %s", call.name)
            return None

        args = call.args
        word = (args.get("word") or "").strip()
        snippet = (args.get("transcript_snippet") or "").strip()
        severity = (args.get("severity") or "").strip().lower()

        if not word:
            logger.info(
                "[supervisor] dropping %s tool call: word empty (args=%s)",
                call.name,
                list(args.keys()),
            )
            return None
        if len(snippet) < _MIN_SNIPPET_CHARS:
            logger.info(
                "[supervisor] dropping %s tool call: snippet too short (%r)",
                call.name,
                snippet,
            )
            return None

        if severity not in _VALID_SEVERITIES:
            severity = "low"

        return StrikeEvent(
            category=category,
            word=word,
            transcript_snippet=snippet,
            severity=severity,
            received_at_ms=call.received_at_ms,
        )
