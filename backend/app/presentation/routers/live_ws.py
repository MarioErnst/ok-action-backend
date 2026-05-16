"""WebSocket router for the Gemini Live streaming evaluator.

One WS per active live session. The client opens it after the parent
live row is already created via POST /live/sessions and pushes raw
audio bytes until the user stops. The server forwards everything to
Gemini Live and pushes back one strike event per detected error.

Protocol on the wire:

  client -> server: {"type": "start", "modules": ["muletillas", ...]} (within 10s)
  server -> client: {"type": "ready"}
  client -> server: <bytes>            # raw 16 kHz mono PCM chunks
  client -> server: {"type": "end"}    # graceful stop from the user
  server -> client: {"type": "strike", ...}    # one per Gemini tool call
  server -> client: {"type": "error", "reason": "..."}  # before close
  server: closes WS

Close codes mirror fluency.py for consistency:
  4001 Unauthorized
  4002 Expected start message
  4003 Invalid parameters (modules / parent live session)
  4500 Internal error

The router never writes to BD. Child rows still come from the existing
composed-eval endpoint that fires after the user stops the session.
The supervisor is purely transport + filter.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.infrastructure.db.session import async_session_factory
from app.infrastructure.security.dependencies import authenticate_ws
from app.use_cases.live.sessions import (
    InvalidParentLiveError,
    validate_parent_live_session,
)
from app.use_cases.live.streaming.supervisor import (
    LiveStreamSupervisor,
    StrikeEvent,
)
from app.use_cases.live.streaming.tools import (
    VALID_LIVE_STREAM_MODULES,
    LiveStreamModule,
)


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/live", tags=["live"])


# Bound how many audio chunks can wait in the in-memory bridge before
# we start dropping the oldest. With 50 ms PCM 16 kHz chunks (1600
# bytes), 64 entries is ~3 s of slack: enough to absorb network jitter,
# small enough to keep latency low if Gemini's WS slows down.
_AUDIO_QUEUE_MAXSIZE = 64


@router.websocket("/sessions/{session_id}/stream")
async def live_session_stream_ws(
    ws: WebSocket,
    session_id: UUID,
    token: str = Query(...),
):
    await ws.accept()

    async with async_session_factory() as auth_db:
        try:
            user = await authenticate_ws(token, auth_db)
        except Exception as exc:
            logger.error("Live WS auth error: %s", exc)
            await ws.close(code=4001, reason="Unauthorized")
            return

    if not user:
        await ws.close(code=4001, reason="Unauthorized")
        return

    try:
        start_msg = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("Live WS start message error: %s", exc)
        await ws.close(code=4002, reason="Expected start message")
        return

    requested_modules = start_msg.get("modules") if isinstance(start_msg, dict) else None
    if not isinstance(requested_modules, list) or not requested_modules:
        await ws.close(code=4003, reason="modules is required")
        return

    invalid = [m for m in requested_modules if m not in VALID_LIVE_STREAM_MODULES]
    if invalid:
        await ws.close(code=4003, reason=f"Invalid modules: {invalid}")
        return

    modules = cast(list[LiveStreamModule], requested_modules)

    async with async_session_factory() as parent_db:
        try:
            await validate_parent_live_session(parent_db, user, session_id)
        except InvalidParentLiveError:
            await ws.close(
                code=4003, reason="session_id is not an active live session"
            )
            return

    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(
        maxsize=_AUDIO_QUEUE_MAXSIZE
    )
    stop_event = asyncio.Event()

    async def deliver_strike(event: StrikeEvent) -> None:
        """Forward one supervisor strike to the client WS."""

        await ws.send_json(
            {
                "type": "strike",
                "category": event.category,
                "word": event.word,
                "transcript_snippet": event.transcript_snippet,
                "severity": event.severity,
                "received_at_ms": event.received_at_ms,
            }
        )

    async def audio_iter():
        """Async iterator that yields chunks until the client signals end."""

        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                return
            yield chunk

    async def read_client() -> None:
        """Pump client WS frames into audio_queue or terminate on end."""

        try:
            while not stop_event.is_set():
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes"):
                    try:
                        audio_queue.put_nowait(message["bytes"])
                    except asyncio.QueueFull:
                        # Drop the oldest to keep up with the upstream.
                        try:
                            audio_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        try:
                            audio_queue.put_nowait(message["bytes"])
                        except asyncio.QueueFull:
                            pass
                    continue
                if message.get("text"):
                    try:
                        data = json.loads(message["text"])
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict) and data.get("type") == "end":
                        break
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.warning("Live WS client read error: %s", exc)
        finally:
            stop_event.set()
            # Sentinel so audio_iter() exits gracefully.
            try:
                audio_queue.put_nowait(None)
            except asyncio.QueueFull:
                # Drop a chunk to make room; the sentinel must reach the
                # supervisor or run() will hang.
                try:
                    audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    audio_queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

    supervisor = LiveStreamSupervisor(modules=modules, strike_sink=deliver_strike)
    await ws.send_json({"type": "ready"})

    reader_task = asyncio.create_task(read_client())
    try:
        await supervisor.run(audio_iter())
    except Exception as exc:
        logger.exception("Live WS supervisor failed: %s", exc)
        try:
            await ws.send_json({"type": "error", "reason": "supervisor_failed"})
        except Exception:
            pass
        await ws.close(code=4500, reason="Internal error")
        reader_task.cancel()
        return
    finally:
        stop_event.set()

    # Drain the reader task so the WS close on the next line does not
    # race with a pending receive.
    reader_task.cancel()
    try:
        await reader_task
    except asyncio.CancelledError:
        pass

    try:
        await ws.send_json({"type": "session_ended"})
    except Exception:
        pass
    try:
        await ws.close()
    except Exception:
        pass
