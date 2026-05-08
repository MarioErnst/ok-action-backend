# Full module documentation: documentacion/modulos/sesion-libre.md
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.precision_round import PrecisionRound
from app.domain.entities.precision_session import PrecisionSession
from app.domain.entities.user import User
from app.infrastructure.ai.linguistic_versatility_gemini import (
    GeminiVersatilityService,
    VersatilityGeminiError,
)
from app.infrastructure.ai.live_gemini import analyze_audio_segment
from app.infrastructure.audio.silence_detector import SilenceDetector
from app.infrastructure.db.session import get_session
from app.infrastructure.security.dependencies import authenticate_ws, get_current_user
from app.presentation.schemas.live_session import LiveSessionListItem
from app.use_cases.live_session.errors import extract_errors_for_dim
from app.use_cases.live_session.prompt_builder import build_system_prompt
from app.use_cases.live_session.save_session import list_live_sessions, save_live_session
from app.use_cases.live_session.session_manager import LiveSessionState
from app.use_cases.precision.abandon_precision_session import abandon_precision_session
from app.use_cases.precision.start_precision_session import start_precision_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live", tags=["live-session"])

ANALYSIS_INTERVAL_SECONDS = 5
VALID_DIMS = {"pron", "acc", "mul", "precision", "lex", "pause"}

# PCM constants at 16kHz 16-bit mono
_QA_CALIBRATION_BYTES = 16000   # 500ms = 16000 bytes
_QA_SILENCE_2S_BYTES = 64000    # 2s = 64000 bytes

# Cap on the lex audio buffer (~30 minutes of 16kHz 16-bit mono PCM = ~57 MB).
# Matches MAX_DURATION_SEC = 300 with headroom; protects RAM if the loop ever
# runs longer than expected.
_LEX_MAX_BYTES = 60 * 1024 * 1024

_versatility_service = GeminiVersatilityService()


@router.websocket("/session")
async def live_session_ws(
    ws: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_session),
):
    await ws.accept()

    try:
        user = await authenticate_ws(token, db)
    except Exception as exc:
        logger.error("WS auth error: %s", exc)
        await ws.close(code=4001, reason="Unauthorized")
        return
    if not user:
        await ws.close(code=4001, reason="Unauthorized")
        return

    # End the read transaction opened by authenticate_ws so qa_mode can commit independently.
    await db.commit()

    try:
        start_msg = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
    except asyncio.TimeoutError:
        await ws.close(code=4002, reason="Expected start message")
        return
    except Exception as exc:
        logger.warning("Unexpected error waiting for start message: %s", exc)
        await ws.close(code=4002, reason="Expected start message")
        return

    dims = start_msg.get("dims", [])
    if not dims or not all(d in VALID_DIMS for d in dims):
        await ws.close(code=4003, reason="Invalid dims")
        return

    # 'precision' has its own QA loop; 'lex' is evaluated only at session
    # close. Both are excluded from the cyclic per-5s analysis.
    standard_dims = [d for d in dims if d not in ("precision", "lex")]
    has_precision = "precision" in dims
    has_lex = "lex" in dims

    state = LiveSessionState(
        user_id=str(user.id),
        selected_dims=dims,
    )
    prompt = build_system_prompt(standard_dims)
    stop_event = asyncio.Event()
    audio_buffer = bytearray()
    qa_buffer = bytearray()
    # Separate buffer that accumulates the entire session audio (never drained
    # mid-session) so the lex evaluation at close can analyze the whole thing.
    lex_buffer = bytearray() if has_lex else None
    answer_done_event = asyncio.Event()

    await ws.send_json({"type": "ready"})

    async def stream_audio():
        """Reads binary audio frames from the client and appends them to the shared buffers."""
        try:
            while not stop_event.is_set():
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    stop_event.set()
                    break
                if message.get("bytes"):
                    audio_buffer.extend(message["bytes"])
                    if has_precision:
                        qa_buffer.extend(message["bytes"])
                    # Cap the lex buffer so a runaway session can't exhaust RAM.
                    # Past the cap we silently drop new bytes — the analysis still
                    # reflects the first 30 minutes of speech, which is plenty.
                    if lex_buffer is not None and len(lex_buffer) < _LEX_MAX_BYTES:
                        lex_buffer.extend(message["bytes"])
                elif message.get("text"):
                    data = json.loads(message["text"])
                    if data.get("type") == "end":
                        state.stop_reason = "user_ended"
                        stop_event.set()
                    elif data.get("type") == "answer_done":
                        answer_done_event.set()
        except WebSocketDisconnect:
            stop_event.set()
        except Exception as exc:
            logger.warning("Audio stream error: %s", exc)
            stop_event.set()

    async def analysis_timer():
        """Every ANALYSIS_INTERVAL_SECONDS, drains the buffer and requests analysis from Gemini."""
        if not standard_dims:
            return
        while not stop_event.is_set():
            await asyncio.sleep(ANALYSIS_INTERVAL_SECONDS)
            if stop_event.is_set():
                break

            # Snapshot and clear atomically between awaits (asyncio is single-threaded)
            chunk = bytes(audio_buffer)
            audio_buffer.clear()

            analysis = await analyze_audio_segment(chunk, standard_dims, prompt)
            if analysis is None:
                continue

            should_stop, reason, dim = state.evaluate_thresholds(analysis)
            await ws.send_json({"type": "analysis", "data": analysis})

            if should_stop:
                state.stop_reason = reason
                await ws.send_json({
                    "type": "correction",
                    "dim": dim,
                    "reason": reason,
                    "errors": extract_errors_for_dim(analysis, dim),
                })
                stop_event.set()

    async def session_limit_timer():
        """Ends session after MAX_DURATION_SEC. Only sets the flag; the finally block sends session_ended."""
        await asyncio.sleep(state.MAX_DURATION_SEC)
        if not stop_event.is_set():
            state.stop_reason = "time_limit"
            stop_event.set()

    async def qa_mode():
        """
        Runs the precision Q&A loop when precision is in selected dims.
        Loads questions, presents them one by one, evaluates answers via Gemini,
        and persists results to the precision_rounds and precision_sessions tables.
        Uses adaptive VAD (SilenceDetector) to auto-detect end of answer.
        """
        qa_session_id: uuid.UUID | None = None
        try:
            qa_session, questions = await start_precision_session(
                db, user.id, total_rounds=5, mode="live_session"
            )
            qa_session_id = qa_session.id
            await db.commit()

            silence_detector = SilenceDetector()
            calibration_done = False
            calibration_buf = bytearray()
            precision_prompt = build_system_prompt(["precision"])

            for idx, question in enumerate(questions):
                if stop_event.is_set():
                    break

                await ws.send_json({
                    "type": "question",
                    "text": question.text,
                    "number": idx + 1,
                    "total": len(questions),
                })

                answer_buf = bytearray()
                consecutive_silence_bytes = 0
                answer_done_event.clear()
                answer_start = datetime.now(timezone.utc)

                while not stop_event.is_set() and not answer_done_event.is_set():
                    chunk = bytes(qa_buffer)
                    qa_buffer.clear()

                    if chunk:
                        if not calibration_done:
                            calibration_buf.extend(chunk)
                            if len(calibration_buf) >= _QA_CALIBRATION_BYTES:
                                silence_detector.calibrate(bytes(calibration_buf))
                                calibration_done = True
                                calibration_buf.clear()
                        else:
                            answer_buf.extend(chunk)
                            if silence_detector.is_silence(chunk):
                                consecutive_silence_bytes += len(chunk)
                                if consecutive_silence_bytes >= _QA_SILENCE_2S_BYTES:
                                    break
                            else:
                                consecutive_silence_bytes = 0

                    await asyncio.sleep(0.1)

                if stop_event.is_set():
                    break

                audio_duration = (datetime.now(timezone.utc) - answer_start).total_seconds()
                audio_bytes = bytes(answer_buf)
                analysis = await analyze_audio_segment(audio_bytes, ["precision"], precision_prompt)

                precision_data: dict = {}
                audio_intelligible = False

                if analysis:
                    precision_data = analysis.get("precision", {})
                    audio_intelligible = bool(precision_data.get("audio_intelligible", False))

                round_obj = PrecisionRound(
                    session_id=qa_session_id,
                    question_id=question.id,
                    question_text=question.text,
                    audio_duration_secs=round(audio_duration, 2),
                    noise_level="low",
                    audio_intelligible=audio_intelligible,
                )
                if audio_intelligible:
                    round_obj.relevance_score = precision_data.get("relevance")
                    round_obj.directness_score = precision_data.get("directness")
                    round_obj.conciseness_score = precision_data.get("conciseness")
                    round_obj.overall_score = precision_data.get("overall")
                    round_obj.feedback = precision_data.get("feedback")
                    session_ref = await db.get(PrecisionSession, qa_session_id)
                    if session_ref:
                        session_ref.completed_rounds += 1
                db.add(round_obj)
                await db.commit()

                if audio_intelligible:
                    await ws.send_json({
                        "type": "round_result",
                        "number": idx + 1,
                        "precision": precision_data,
                    })
                else:
                    await ws.send_json({"type": "round_unintelligible", "number": idx + 1})

            if not stop_event.is_set() and qa_session_id:
                session_ref = await db.get(PrecisionSession, qa_session_id)
                if session_ref:
                    session_ref.status = "completed"
                    session_ref.completed_at = datetime.now(timezone.utc)
                await db.commit()
                await ws.send_json({"type": "session_complete"})

        except Exception as exc:
            logger.error("Q&A mode error: %s", exc)
        finally:
            if qa_session_id:
                try:
                    await abandon_precision_session(db, qa_session_id)
                    await db.commit()
                except Exception:
                    pass
            stop_event.set()

    tasks = [stream_audio(), analysis_timer(), session_limit_timer()]
    if has_precision:
        tasks.append(qa_mode())

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.error("Unexpected error in live session: %s", exc)
    finally:
        if not state.stop_reason:
            state.stop_reason = "user_ended"

        # If lex was selected, run a single end-of-session versatility analysis
        # over the entire accumulated audio. We do this BEFORE session_ended so
        # the client receives the lex_result message in the same connection.
        # Failure here is non-fatal: log it, send no lex_result, save the rest.
        if lex_buffer is not None and len(lex_buffer) > 0:
            try:
                lex_data = await _versatility_service.evaluate_free(
                    bytes(lex_buffer), "audio/pcm;rate=16000"
                )
                state.lex_result = lex_data
                try:
                    await ws.send_json({"type": "lex_result", "data": lex_data})
                except Exception:
                    pass
            except VersatilityGeminiError as exc:
                logger.warning("Versatility analysis failed: %s", exc)
            except Exception as exc:
                logger.error("Unexpected versatility analysis error: %s", exc)

        # Send session_ended after lex_result so the client knows the order:
        # any lex_result message arrives strictly before the terminal event.
        # The DB operation outlives the WebSocket connection.
        try:
            await ws.send_json({"type": "session_ended", "reason": state.stop_reason})
            await ws.close()
        except Exception:
            pass
        try:
            await save_live_session(state, user, db)
        except Exception as exc:
            logger.error("Failed to save live session: %s", exc)


@router.get("/sessions", response_model=list[LiveSessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    sessions = await list_live_sessions(user, db)
    return [
        LiveSessionListItem(
            id=str(s.id),
            selected_dims=s.selected_dims,
            overall_score=float(s.overall_score) if s.overall_score else None,
            stop_reason=s.stop_reason,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]
