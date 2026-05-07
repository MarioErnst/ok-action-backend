import math
import struct
from app.infrastructure.audio.silence_detector import SilenceDetector


def _pcm_chunk(rms_target: float, num_samples: int = 8000) -> bytes:
    """Generate a PCM 16-bit chunk with approximately the given RMS."""
    amplitude = int(rms_target * math.sqrt(2))
    samples = []
    for i in range(num_samples):
        s = int(amplitude * math.sin(2 * math.pi * 440 * i / 16000))
        samples.append(max(-32768, min(32767, s)))
    return struct.pack(f"{num_samples}h", *samples)


def test_default_ambient_floor_is_conservative():
    detector = SilenceDetector()
    # Default floor = 300.0; threshold = 300 * 3.98 ≈ 1194
    # RMS 400 < 1194 → silence
    chunk = _pcm_chunk(rms_target=400)
    assert detector.is_silence(chunk) is True


def test_calibrate_sets_floor():
    detector = SilenceDetector()
    loud_chunk = _pcm_chunk(rms_target=600)
    detector.calibrate(loud_chunk)
    # After calibration with RMS ~600, threshold ≈ 600 * 3.98 = 2388
    # A chunk with RMS=400 should be silence
    quiet_chunk = _pcm_chunk(rms_target=400)
    assert detector.is_silence(quiet_chunk) is True


def test_voice_above_threshold_is_not_silence():
    detector = SilenceDetector()
    detector.calibrate(_pcm_chunk(rms_target=100))  # quiet room
    # threshold = 100 * 3.98 = 398; voice at RMS 1000 > 398
    voice_chunk = _pcm_chunk(rms_target=1000)
    assert detector.is_silence(voice_chunk) is False


def test_empty_chunk_does_not_crash():
    detector = SilenceDetector()
    detector.calibrate(b"")  # should not raise
    assert detector.is_silence(b"") is True  # empty = silence
