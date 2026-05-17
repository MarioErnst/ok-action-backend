"""Per-session orchestrator that bridges the browser WS to AssemblyAI.

One supervisor instance lives for the duration of one live session.
Responsibilities:

1. Forward inbound PCM audio chunks (from the client WS) into the
   AssemblyAI streaming session.
2. Consume final transcripts from AssemblyAI, run them through the
   Spanish muletilla matcher, and emit one StrikeEvent per filler
   occurrence back to the client WS.
3. Persist nothing. The composed-eval endpoint is still the single
   source of truth for child sessions in the database; the supervisor
   only orchestrates real-time signals for the live "corten".

Why AssemblyAI replaced Gemini Live here: Gemini Live is a
conversational model that, when forced to evaluate audio on a timer,
hallucinated tool calls (it would "complete" expected speech patterns
with imaginary muletillas). AssemblyAI is a transcriber — it returns
what it actually heard, never invents. Combined with a Spanish filler
dictionary, every emitted strike is grounded in a real transcript
token.

Module scope: today the supervisor only handles muletillas. The
LiveStreamModule union is intentionally narrow. Pronunciation and
accentuation evaluation continue to live in the composed-eval flow
at session end (no live "corten" for those modules).

Composition with the existing pipeline:
- start_live_session creates the parent row in BD; the supervisor
  attaches via session_id and never writes to BD.
- The client opens the WS after start() succeeds; the supervisor
  authenticates via the FastAPI dependency before instantiating.
- On client disconnect, the supervisor closes the AssemblyAI WS and
  returns. The router handler runs no extra cleanup.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from app.infrastructure.ai.live_stream_assemblyai import (
    AssemblyAIStreamingSession,
)
from app.use_cases.live.streaming.muletillas_dictionary import (
    MuletillaMatch,
    extract_muletillas,
)


logger = logging.getLogger(__name__)


# The supervisor exposes the same `LiveStreamModule` shape as before
# so the router payload stays stable, but the only category we emit
# today is muletillas. Pronunciation and accentuation moved to the
# composed-eval flow that runs at session end.
LiveStreamModule = Literal["muletillas"]


VALID_LIVE_STREAM_MODULES: tuple[LiveStreamModule, ...] = ("muletillas",)


@dataclass(frozen=True)
class StrikeEvent:
    """Strike event the supervisor emits towards the client.

    `category` matches the LiveStreamModule literal and the frontend's
    StreamingStrikeCategory. `word` is the canonical muletilla form
    (e.g. "eh", "o sea"). `transcript_snippet` carries enough context
    for the UI to render the surrounding sentence fragment. `severity`
    is always "low" for now — the dictionary matcher does not weigh
    occurrences. We keep the field in the payload because the wire
    contract is shared with the frontend, which may color the chip
    differently per severity.
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


# Severity default for every dictionary match. AssemblyAI returns a
# literal transcript so we have no per-occurrence severity signal; the
# frontend can derive its own severity later (e.g. raise it after the
# same muletilla repeats N times) if pedagogy requires it.
_DEFAULT_SEVERITY = "low"


class LiveStreamSupervisor:
    """Orchestrates one live streaming session."""

    def __init__(
        self,
        modules: list[LiveStreamModule],
        strike_sink: StrikeSink,
    ):
        if not modules:
            raise ValueError("supervisor requires at least one module")
        invalid = [m for m in modules if m not in VALID_LIVE_STREAM_MODULES]
        if invalid:
            raise ValueError(
                f"supervisor received unsupported modules: {invalid}"
            )
        self._modules = modules
        self._strike_sink = strike_sink
        self._receive_task: asyncio.Task | None = None
        # Session totals surfaced in the closing log so a single line at
        # the end of each session reports everything we care about for
        # diagnostics (chunks streamed, transcripts received, strikes
        # emitted, strikes dropped by the sink).
        self._transcripts_received = 0
        self._strikes_emitted = 0
        self._sink_errors = 0

    async def run(self, audio_iter) -> None:
        """Drive the session until audio_iter ends or AssemblyAI dies.

        `audio_iter` is an async iterator of raw PCM byte chunks coming
        from the browser. We spawn a parallel task that listens to
        AssemblyAI's final transcripts and forwards strikes, then
        sequentially pump audio until the client stops sending.
        Returning from this method tears down both ends.

        Errors propagate. The router wraps run() in a try/except so
        the client WS gets a clean close frame on failure.
        """

        logger.info("[supervisor] starting (modules=%s)", self._modules)
        session = AssemblyAIStreamingSession()
        async with session.open() as s:
            self._receive_task = asyncio.create_task(self._receive_loop(s))
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
                    await s.send_audio_chunk(chunk)
                logger.info(
                    "[supervisor] audio iterator drained after %d chunks / %d bytes",
                    chunks_received,
                    bytes_received,
                )
            finally:
                if self._receive_task and not self._receive_task.done():
                    self._receive_task.cancel()
                    try:
                        await self._receive_task
                    except asyncio.CancelledError:
                        pass
                self._receive_task = None
                logger.info(
                    "[supervisor] finished (chunks_in=%d transcripts=%d strikes=%d sink_errors=%d)",
                    chunks_received,
                    self._transcripts_received,
                    self._strikes_emitted,
                    self._sink_errors,
                )

    async def _receive_loop(
        self, session: AssemblyAIStreamingSession
    ) -> None:
        """Consume final transcripts from AssemblyAI."""

        logger.info("[supervisor] receive loop started")
        try:
            async for transcript in session.iter_final_transcripts():
                await self._process_transcript(transcript)
        finally:
            logger.info("[supervisor] receive loop ended")

    async def _process_transcript(self, transcript: str) -> None:
        """Run the matcher and emit a strike per detected muletilla."""

        self._transcripts_received += 1
        matches = extract_muletillas(transcript)
        if not matches:
            return
        for match in matches:
            event = self._build_event(match)
            self._strikes_emitted += 1
            logger.info(
                "[supervisor] STRIKE category=%s word=%r snippet=%r",
                event.category,
                event.word,
                event.transcript_snippet,
            )
            try:
                await self._strike_sink(event)
            except Exception as exc:
                self._sink_errors += 1
                logger.warning("[supervisor] strike sink raised: %s", exc)

    def _build_event(self, match: MuletillaMatch) -> StrikeEvent:
        return StrikeEvent(
            category="muletillas",
            word=match.word,
            transcript_snippet=match.context_snippet,
            severity=_DEFAULT_SEVERITY,
            received_at_ms=int(time.time() * 1000),
        )
