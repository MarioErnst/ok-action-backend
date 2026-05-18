"""Thin async wrapper around the AssemblyAI streaming v3 SDK.

The AssemblyAI Python SDK is synchronous and callback-driven: you
register handlers with `client.on(Event, handler)` and then drive the
client with blocking calls (`connect`, `stream`, `disconnect`). For
the supervisor — which is async first — we adapt that surface with
two patterns:

- Run every blocking call inside `asyncio.to_thread` so we never stall
  the event loop on the SDK's internal WebSocket I/O.
- Marshal the callbacks back into asyncio with `call_soon_threadsafe`
  + `asyncio.Queue`, then expose `iter_final_transcripts` as an
  ordinary async iterator the supervisor can `async for` over.

Why we wrap the SDK at all instead of hand-rolling the WebSocket:
- It manages the wire protocol, automatic reconnects, audio chunk
  pacing, and — critically — sends `Terminate` reliably on
  `disconnect(terminate=True)`. An abandoned AssemblyAI session keeps
  billing until the 3-hour cap, so getting Terminate right is worth
  the SDK dependency.
- It will track new server features as AssemblyAI ships them.

What we do wrap:
- Both partial and final TurnEvents. Final turns are still the
  authoritative source for transcription, but partials are emitted as
  the model recognizes new audio (every ~100-300 ms). The supervisor
  runs the matcher on each partial and uses a per-turn stability
  tracker to decide which matches are confirmed enough to fire a
  strike before the turn closes — without that we depend on a user
  pause for the corten to ever fire, which is exactly the failure
  mode users hit in fluent free-speech sessions.

What we do not wrap:
- Errors at the SDK level. We log them and drain the iterator; the
  supervisor decides what to do (today it tears down the session).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator

from assemblyai.streaming.v3 import (
    StreamingClient,
    StreamingClientOptions,
    StreamingEvents,
    StreamingParameters,
    TurnEvent,
)

from config import settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnTranscript:
    """One transcript update from AssemblyAI.

    `is_final` distinguishes between live partials (which get
    rewritten as the model gains context) and the authoritative
    final emitted when the turn closes. The supervisor uses the
    partials to fire early strikes and the final as the source of
    truth for any match that did not stabilize through partials.
    """

    text: str
    is_final: bool


# Universal-3 Pro Streaming model id, pinned (CLAUDE.md rule against
# *-latest aliases). The Python SDK takes the value as a raw string.
_MODEL = "u3-rt-pro"


# Audio format the front-end already produces and AssemblyAI expects.
_SAMPLE_RATE = 16_000


# Maximum silence (ms) before AssemblyAI is forced to close a turn even
# when the smart detector has not reached its confidence threshold. The
# server default is ~2400 ms; we tightened it to 400 ms because real
# users speak fluently without long pauses and the previous 800 ms
# value still let the smart detector wait through a full 20 s discourse
# before closing the first turn. With 400 ms any short breath closes
# a turn and the corten reacts within ~1 s of the first filler.
_MAX_TURN_SILENCE_MS = 400


# Confidence the smart detector must reach (0-1) to close a turn on its
# own. The server default is ~0.7; we relaxed it to 0.4 so the detector
# also closes on lower-confidence prosodic boundaries (e.g. a hesitation
# followed by a content word). Combined with the lower max_turn_silence
# this maximizes the chance of emitting an intermediate turn while the
# user is still speaking.
_END_OF_TURN_CONFIDENCE_THRESHOLD = 0.4


# Prompt steers the model into verbatim Spanish (Latin American). The
# muletilla list is repeated here so the model preserves them in the
# transcript instead of cleaning them up — see Universal-3 Pro
# prompting guide. Keep the prompt short; long prompts increase
# first-turn latency.
_LIVE_PROMPT = (
    "Transcribe Spanish (Latin American) verbatim with standard "
    "punctuation. Preserve every filler word and hesitation exactly "
    "as spoken: eh, ehh, este, esto, esta, mmm, mm, ah, ahh, o sea, "
    "viste, tipo, pues, digamos. Never collapse or normalize fillers."
)


# Keyterms get boosted by the recognizer. We list the same fillers
# plus their common variants so AssemblyAI is more likely to surface
# them in the transcript. Streaming cap is 100 terms / 50 chars each.
_KEYTERMS: list[str] = [
    "eh",
    "ehh",
    "este",
    "esto",
    "esta",
    "mmm",
    "mm",
    "ah",
    "ahh",
    "o sea",
    "viste",
    "tipo",
    "pues",
    "digamos",
]


class AssemblyAIStreamingSession:
    """Owns one AssemblyAI streaming session for one live session.

    Usage from the supervisor:

        async with AssemblyAIStreamingSession().open() as session:
            asyncio.create_task(forward_chunks(session))
            async for turn in session.iter_turn_transcripts():
                ...  # turn.text + turn.is_final
    """

    def __init__(self):
        self._client = StreamingClient(
            StreamingClientOptions(api_key=settings.assemblyai_api_key)
        )
        # Queue of turn transcripts (partial or final) the SDK delivers
        # via callbacks. `None` is the close sentinel used by `aclose`.
        self._turn_queue: asyncio.Queue[TurnTranscript | None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = False

    def open(self) -> "_AssemblyAIOpenContext":
        return _AssemblyAIOpenContext(self)

    async def _enter(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._turn_queue = asyncio.Queue()
        self._wire_handlers()

        params = StreamingParameters(
            sample_rate=_SAMPLE_RATE,
            speech_model=_MODEL,
            prompt=_LIVE_PROMPT,
            keyterms_prompt=_KEYTERMS,
            max_turn_silence=_MAX_TURN_SILENCE_MS,
            end_of_turn_confidence_threshold=_END_OF_TURN_CONFIDENCE_THRESHOLD,
            include_partial_turns=True,
        )
        logger.info(
            "[live-assemblyai] opening Streaming WS (model=%s, sample_rate=%d, "
            "max_turn_silence=%dms, end_of_turn_confidence_threshold=%.2f, "
            "partials=on)",
            _MODEL,
            _SAMPLE_RATE,
            _MAX_TURN_SILENCE_MS,
            _END_OF_TURN_CONFIDENCE_THRESHOLD,
        )
        # connect() is a blocking handshake; offload to a worker thread
        # so the event loop keeps serving other tasks.
        await asyncio.to_thread(self._client.connect, params)
        self._connected = True
        logger.info("[live-assemblyai] Streaming WS opened")

    def _wire_handlers(self) -> None:
        """Register SDK callbacks that publish into the async queue."""

        def on_turn(_self, event: TurnEvent) -> None:
            transcript = (event.transcript or "").strip()
            if not transcript:
                return
            # Partials arrive very frequently (every ~100-300 ms) so we
            # keep the log line compact. Finals stay loud because they
            # are the audit point and far less frequent.
            if event.end_of_turn:
                logger.info(
                    "[live-assemblyai] turn final: %r", transcript
                )
            else:
                logger.debug(
                    "[live-assemblyai] turn partial: %r", transcript
                )
            self._publish(
                TurnTranscript(text=transcript, is_final=bool(event.end_of_turn))
            )

        def on_error(_self, error) -> None:
            logger.warning("[live-assemblyai] error event: %s", error)
            # Surface as end-of-stream so the supervisor unwinds cleanly.
            self._publish(None)

        def on_termination(_self, _event) -> None:
            logger.info("[live-assemblyai] termination event received")
            self._publish(None)

        self._client.on(StreamingEvents.Turn, on_turn)
        self._client.on(StreamingEvents.Error, on_error)
        self._client.on(StreamingEvents.Termination, on_termination)

    def _publish(self, item: TurnTranscript | None) -> None:
        """Marshal a value from any thread into the async queue."""

        if self._loop is None or self._turn_queue is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._turn_queue.put_nowait, item)
        except RuntimeError:
            # Loop is already closed (we are tearing down). Drop.
            pass

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Forward a raw 16 kHz mono PCM chunk to AssemblyAI.

        Empty chunks are ignored. Calls fall through silently if the
        client is not connected yet (shouldn't happen in normal flow
        but keeps us robust against races during teardown).
        """

        if not pcm_bytes or not self._connected:
            return
        await asyncio.to_thread(self._client.stream, pcm_bytes)

    async def iter_turn_transcripts(self) -> AsyncIterator[TurnTranscript]:
        """Yield each turn transcript the model emits (partial or final).

        Returns when the SDK signals termination or an error.
        """

        if self._turn_queue is None:
            raise RuntimeError("AssemblyAIStreamingSession is not open")
        while True:
            item = await self._turn_queue.get()
            if item is None:
                return
            yield item

    async def aclose(self) -> None:
        """Disconnect cleanly. Always sends Terminate.

        Critical: an abandoned session keeps billing for up to three
        hours per the AssemblyAI streaming docs. The `terminate=True`
        flag ensures the SDK emits the closing message before tearing
        the socket down.
        """

        if not self._connected:
            return
        logger.info("[live-assemblyai] closing Streaming WS")
        try:
            await asyncio.to_thread(self._client.disconnect, True)
        except Exception as exc:
            logger.warning("[live-assemblyai] error during disconnect: %s", exc)
        finally:
            self._connected = False
            # Unblock any consumer still awaiting on the queue.
            self._publish(None)
            logger.info("[live-assemblyai] Streaming WS closed")


class _AssemblyAIOpenContext:
    """Async context manager around `AssemblyAIStreamingSession`."""

    def __init__(self, owner: AssemblyAIStreamingSession):
        self._owner = owner

    async def __aenter__(self) -> AssemblyAIStreamingSession:
        await self._owner._enter()
        return self._owner

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._owner.aclose()
