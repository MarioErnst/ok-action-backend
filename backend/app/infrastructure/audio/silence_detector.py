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


# dB above ambient floor required to classify audio as non-silence.
# 12 dB corresponds to a linear factor of ~3.98, which gives enough headroom
# over typical background noise without being so strict that real speech is missed.
SILENCE_MARGIN_DB = 12.0


class SilenceDetector:
    """
    Adaptive VAD for Live Session Q&A mode.
    Calibrates against ambient noise at session start so that background noise
    does not prevent silence detection.
    """

    def __init__(self) -> None:
        # Conservative default so an uncalibrated detector treats most audio as silence
        # rather than triggering false positives on noise.
        self._ambient_floor_rms: float = 300.0

    def calibrate(self, audio_chunk: bytes) -> None:
        """
        Update the ambient noise floor using a representative audio chunk.

        Args:
            audio_chunk: Raw 16-bit signed PCM bytes captured during a quiet moment.
        """
        samples = self._parse_pcm(audio_chunk)
        if not samples:
            return
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        self._ambient_floor_rms = rms

    def is_silence(self, audio_chunk: bytes) -> bool:
        """
        Return True when the chunk's RMS is below the adaptive silence threshold.

        Args:
            audio_chunk: Raw 16-bit signed PCM bytes to evaluate.

        Returns:
            True if the audio is considered silence, False otherwise.
        """
        samples = self._parse_pcm(audio_chunk)
        if not samples:
            return True
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        # Convert dB margin to a linear multiplier: 10^(dB/20)
        threshold = self._ambient_floor_rms * (10 ** (SILENCE_MARGIN_DB / 20))
        return rms < threshold

    @property
    def ambient_floor_rms(self) -> float:
        """Current ambient noise floor in RMS units."""
        return self._ambient_floor_rms

    @staticmethod
    def _parse_pcm(audio_chunk: bytes) -> list[int]:
        """
        Decode raw bytes as 16-bit signed PCM samples (little-endian).

        Args:
            audio_chunk: Raw PCM bytes.

        Returns:
            List of integer sample values, or empty list for invalid input.
        """
        if not audio_chunk or len(audio_chunk) < 2:
            return []
        n = len(audio_chunk) // 2
        return list(struct.unpack(f"{n}h", audio_chunk[: n * 2]))
