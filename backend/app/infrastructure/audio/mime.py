from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

# Allowlist of audio MIME base types accepted by Gemini and emitted by the
# browsers we support (Chrome, Firefox, iOS Safari, Android Chrome). Codec
# parameters (e.g. ";codecs=opus") are stripped before matching.
ALLOWED_AUDIO_MIMES: frozenset[str] = frozenset(
    {
        "audio/webm",
        "audio/mp4",
        "audio/ogg",
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
    }
)


def verify_audio_mime(audio: UploadFile) -> str:
    """Validate the uploaded audio MIME type against the allowlist.

    Returns the normalized base MIME (without codec parameters) for downstream
    Gemini calls. Raises 415 if the type is missing or unsupported, replacing
    the previous silent fallback to "audio/webm" that could surface as opaque
    Gemini 502s when a browser sent an exotic content-type.
    """

    raw = audio.content_type or ""
    base = raw.split(";", 1)[0].strip().lower()
    if base not in ALLOWED_AUDIO_MIMES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo de audio no soportado: {raw or 'desconocido'}",
        )
    return base
