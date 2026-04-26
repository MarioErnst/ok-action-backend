import asyncio
import math
import struct
import tempfile
import os


async def is_silent(audio_bytes: bytes, mime_type: str, rms_threshold: float = 300.0) -> bool:
    """
    Returns True if the audio contains no meaningful speech energy.
    Uses ffmpeg to decode any format to raw PCM s16le, then calculates RMS.
    rms_threshold: values below this (out of 32767) are considered silence.
    """
    suffix = _mime_to_extension(mime_type)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", tmp_path,
            "-ar", "16000",
            "-ac", "1",
            "-f", "s16le",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        pcm_data, _ = await process.communicate()
    finally:
        os.unlink(tmp_path)

    if not pcm_data or len(pcm_data) < 2:
        return True

    samples = struct.unpack(f"{len(pcm_data) // 2}h", pcm_data)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return rms < rms_threshold


def _mime_to_extension(mime_type: str) -> str:
    mapping = {
        "audio/webm": ".webm",
        "audio/mp4": ".mp4",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/x-m4a": ".m4a",
    }
    return mapping.get(mime_type, ".audio")
