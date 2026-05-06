import pytest
from unittest.mock import AsyncMock, patch

from app.infrastructure.ai.precision_gemini import GeminiPrecisionService, PrecisionGeminiError


@pytest.mark.asyncio
async def test_returns_unintelligible_on_flag():
    service = GeminiPrecisionService()
    mock_parsed = {
        "transcript": "",
        "relevance_score": 0,
        "directness_score": 0,
        "conciseness_score": 0,
        "feedback": "",
        "strengths": [],
        "improvement_areas": [],
        "audio_intelligible": False,
    }
    with patch.object(service, "_call_gemini", new=AsyncMock(return_value=mock_parsed)):
        result = await service.evaluate_response(b"audio", "audio/webm", "¿Qué aprendiste?")
    assert result["audio_intelligible"] is False
    assert result["relevance_score"] == 0


@pytest.mark.asyncio
async def test_raises_on_gemini_exception():
    service = GeminiPrecisionService()
    with patch.object(service, "_call_gemini", new=AsyncMock(side_effect=Exception("API error"))):
        with pytest.raises(PrecisionGeminiError):
            await service.evaluate_response(b"audio", "audio/webm", "¿Qué aprendiste?")
