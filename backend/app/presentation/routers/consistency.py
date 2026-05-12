from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.consistency_metrics import ConsistencyMetrics
from app.domain.entities.enums import SessionStatusEnum
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.ai.consistency_gemini import analyze_consistency_audio
from app.infrastructure.db.session import async_session_factory, get_session
from app.infrastructure.security.dependencies import authenticate_ws, get_current_user
from app.use_cases.live.sessions import (
    InvalidParentLiveError,
    validate_parent_live_session,
)
from app.presentation.schemas.consistency import (
    ConsistencyMetricsOutput,
    ConsistencySessionDetail,
    ConsistencySessionListItem,
)
from app.use_cases.consistency.prompt_builder import build_consistency_prompt
from app.use_cases.consistency.session_manager import (
    MIN_AUDIO_BYTES,
    ConsistencySessionState,
    build_no_audio_analysis,
)
from app.use_cases.consistency.sessions import (
    get_consistency_session,
    list_consistency_sessions,
    persist_consistency_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/consistency", tags=["consistency"])


def _build_detail(
    session_row: Session, metrics_row: ConsistencyMetrics
) -> ConsistencySessionDetail:
    return ConsistencySessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        duration_ms=session_row.duration_ms,
        score=session_row.score,
        status=session_row.status,
        created_at=session_row.created_at,
        metrics=ConsistencyMetricsOutput.model_validate(metrics_row),
    )


def _stop_reason_to_status(reason: str | None) -> SessionStatusEnum:
    """Map the WS stop reason to the persisted session status.

    Same convention as fluency: user_ended/time_limit -> completed,
    everything else (disconnect, error, unknown) -> aborted.
    """

    if reason in ("user_ended", "time_limit"):
        return SessionStatusEnum.completed
    return SessionStatusEnum.aborted


@router.websocket("/session")
async def consistency_session_ws(
    ws: WebSocket,
    token: str = Query(...),
):
    """Single-shot consistency evaluation over a WebSocket.

    Unlike fluency, consistency analyzes the full audio buffer once at the
    end (Gemini compares opening/middle/closing as one piece). The WS
    streams audio for up to MAX_DURATION_SEC, then on close runs Gemini
    once and persists if the analysis succeeded.

    Protocol:
      client -> server: {"type": "start", "prompt_text": "..."} (within 10s)
      server -> client: {"type": "ready"}
      client -> server: <bytes>
      client -> server: {"type": "end"}
      server -> client: {"type": "analysis", "data": {...}}
      server -> client: {"type": "warning", "reason": "...", "data": {...}}
      server -> client: {"type": "session_ended", "reason": "...", "score": N|null,
                         "session_id": UUID|null}
      server: closes WS
    """

    await ws.accept()

    async with async_session_factory() as auth_db:
        try:
            user = await authenticate_ws(token, auth_db)
        except Exception as exc:
            logger.error("Consistency WS auth error: %s", exc)
            await ws.close(code=4001, reason="Unauthorized")
            return

    if not user:
        await ws.close(code=4001, reason="Unauthorized")
        return

    try:
        start_msg = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("Consistency start message error: %s", exc)
        await ws.close(code=4002, reason="Expected start message")
        return

    prompt_text = str(start_msg.get("prompt_text") or "").strip()

    # Validate parent_id before sending "ready" so a bad parent_id closes
    # the WS cleanly without the client thinking the session is live.
    parent_id_raw = start_msg.get("parent_id")
    parent_id: UUID | None = None
    if parent_id_raw:
        try:
            parent_id = UUID(str(parent_id_raw))
        except (ValueError, TypeError):
            await ws.close(code=4003, reason="parent_id is not a valid UUID")
            return
        async with async_session_factory() as parent_db:
            try:
                await validate_parent_live_session(parent_db, user, parent_id)
            except InvalidParentLiveError:
                await ws.close(code=4003, reason="parent_id is not an active live session")
                return

    state = ConsistencySessionState(user_id=str(user.id), prompt_text=prompt_text)
    prompt = build_consistency_prompt(prompt_text)
    stop_event = asyncio.Event()
    audio_buffer = bytearray()

    await ws.send_json({"type": "ready"})

    async def stream_audio():
        try:
            while not stop_event.is_set():
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    state.stop_reason = "disconnect"
                    stop_event.set()
                    break
                if message.get("bytes"):
                    audio_buffer.extend(message["bytes"])
                    continue
                if message.get("text"):
                    data = json.loads(message["text"])
                    if data.get("type") == "end":
                        state.stop_reason = "user_ended"
                        stop_event.set()
        except WebSocketDisconnect:
            state.stop_reason = "disconnect"
            stop_event.set()
        except Exception as exc:
            logger.warning("Consistency audio stream error: %s", exc)
            state.stop_reason = "error"
            stop_event.set()

    async def session_limit_timer():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=state.MAX_DURATION_SEC)
        except asyncio.TimeoutError:
            state.stop_reason = "time_limit"
            stop_event.set()

    try:
        await asyncio.gather(stream_audio(), session_limit_timer(), return_exceptions=True)
    except Exception as exc:
        logger.error("Unexpected consistency session error: %s", exc)
    finally:
        # Conservative default: paths that did not set a reason explicitly
        # should map to aborted, not silently pass as completed.
        if not state.stop_reason:
            state.stop_reason = "unknown"

        ended_at = datetime.now(timezone.utc)
        audio_bytes = bytes(audio_buffer)
        analysis: dict | None = None

        if len(audio_bytes) < MIN_AUDIO_BYTES:
            analysis = build_no_audio_analysis()
        else:
            analysis = await analyze_consistency_audio(audio_bytes, prompt)

        # Two distinct cases for "no row in DB":
        # - analysis is None: Gemini failed (already logged inside the helper).
        # - audio_bytes < MIN: build_no_audio_analysis returns a placeholder
        #   with audio_intelligible=false; we choose not to persist these
        #   to keep the timeline free of empty attempts.
        should_persist = (
            analysis is not None
            and analysis.get("audio_intelligible") is True
        )

        persisted_id: UUID | None = None
        if should_persist:
            try:
                async with async_session_factory() as persist_db:
                    result = await persist_consistency_session(
                        db=persist_db,
                        user=user,
                        started_at=state.started_at,
                        ended_at=ended_at,
                        status=_stop_reason_to_status(state.stop_reason),
                        analysis=analysis,
                        parent_id=parent_id,
                    )
                    if result is not None:
                        persisted_id = result[0].id
            except Exception as exc:
                logger.error("Consistency persistence failed: %s", exc)

        # Guard the close-time messaging with a single try/except. Avoid an
        # early return inside finally (Python warns and any pending exception
        # would be silently swallowed).
        try:
            if analysis is None:
                await ws.send_json({"type": "error", "message": "No se pudo analizar la consistencia."})
            else:
                state.set_analysis(analysis)
                warning_reason = state.warning_reason()
                await ws.send_json({"type": "analysis", "data": analysis})
                if warning_reason:
                    await ws.send_json({"type": "warning", "reason": warning_reason, "data": analysis})
                await ws.send_json({
                    "type": "session_ended",
                    "reason": state.stop_reason,
                    "score": state.final_score(),
                    "session_id": str(persisted_id) if persisted_id else None,
                })
            await ws.close()
        except Exception:
            pass


# HTTP history endpoints


@router.get("/sessions", response_model=list[ConsistencySessionListItem])
async def list_sessions_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[ConsistencySessionListItem]:
    rows = await list_consistency_sessions(db=db, user=user)
    return [
        ConsistencySessionListItem(
            id=session_row.id,
            started_at=session_row.started_at,
            ended_at=session_row.ended_at,
            duration_ms=session_row.duration_ms,
            score=session_row.score,
            status=session_row.status,
            consistency_score=metrics_row.consistency_score,
            volatility_score=metrics_row.volatility_score,
            active_pct=metrics_row.active_pct,
        )
        for session_row, metrics_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=ConsistencySessionDetail)
async def get_session_endpoint(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ConsistencySessionDetail:
    found = await get_consistency_session(db=db, user=user, session_id=session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de consistencia no encontrada",
        )
    return _build_detail(*found)
