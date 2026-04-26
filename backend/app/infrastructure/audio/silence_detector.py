import asyncio
import logging
import math
import os
import struct
import tempfile

logger = logging.getLogger(__name__)


async def is_silent(audio_bytes: bytes, mime_type: str, rms_threshold: float = 300.0) -> bool:
    """
    Returns True only when silence is confirmed via RMS analysis.
    On any technical failure (ffmpeg error, decode error), returns False
    to avoid blocking valid recordings.
    """
    if not audio_bytes:
        return True

    suffix = _mime_to_extension(mime_type)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i", tmp_path,
            "-ar", "16000",
            "-ac", "1",
            "-f", "s16le",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        pcm_data, stderr_data = await process.communicate()

        if process.returncode != 0:
            logger.warning(
                "ffmpeg failed decoding audio (code %d): %s",
                process.returncode,
                stderr_data.decode(errors="replace")[:300],
            )
            return False

    finally:
        os.unlink(tmp_path)

    if not pcm_data or len(pcm_data) < 2:
        logger.warning("ffmpeg produced no PCM output for mime_type=%s", mime_type)
        return False

    samples = struct.unpack(f"{len(pcm_data) // 2}h", pcm_data)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    logger.debug("Audio RMS=%.1f threshold=%.1f", rms, rms_threshold)
    return rms < rms_threshold


def _mime_to_extension(mime_type: str) -> str:
    base_type = mime_type.split(";")[0].strip()
    mapping = {
        "audio/webm": ".webm",
        "audio/mp4": ".mp4",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/x-m4a": ".m4a",
        "video/webm": ".webm",
    }
    return mapping.get(base_type, ".webm")
