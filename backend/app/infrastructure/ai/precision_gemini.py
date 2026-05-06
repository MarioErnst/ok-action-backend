# Gemini-based evaluator for precision (relevance, directness, conciseness) of oral responses.
# Full docs: documentacion/modulos/evaluacion-precision.md
from google import genai
from google.genai import types

from config import settings

PRECISION_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=[
        "transcript", "relevance_score", "directness_score",
        "conciseness_score", "feedback", "strengths",
        "improvement_areas", "audio_intelligible",
    ],
    properties={
        "transcript": types.Schema(type=types.Type.STRING),
        "relevance_score": types.Schema(type=types.Type.INTEGER),
        "directness_score": types.Schema(type=types.Type.INTEGER),
        "conciseness_score": types.Schema(type=types.Type.INTEGER),
        "feedback": types.Schema(type=types.Type.STRING),
        "strengths": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
        "improvement_areas": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
        "audio_intelligible": types.Schema(type=types.Type.BOOLEAN),
    },
)

_PROMPT_TEMPLATE = """\
Eres un evaluador de comunicación oral en español. Se le hizo la siguiente pregunta al estudiante:

"{question}"

Evalúa la precisión de su respuesta en tres dimensiones (0-100 cada una):
- relevance_score: ¿Respondió la pregunta sin irse por las ramas? (0=completamente fuera de tema, 100=perfectamente relevante)
- directness_score: ¿Llegó al punto rápido sin rodeos ni preámbulos? (0=muy indirecto, 100=directo al grano)
- conciseness_score: ¿Evitó repetir ideas o usar palabras de relleno innecesarias? (0=muy repetitivo/verboso, 100=perfectamente conciso)

IMPORTANTE:
- NO penalices por ruido de fondo ni calidad de audio.
- Si el habla es ininteligible o la persona no habló, establece audio_intelligible en false y todos los scores en 0.
- Si puedes evaluar el habla, establece audio_intelligible en true.
- Escribe feedback, strengths e improvement_areas en español.
"""


class PrecisionGeminiError(Exception):
    """Raised when the Gemini precision evaluation call fails."""


class GeminiPrecisionService:
    """Evaluates the precision of a spoken response using the Gemini API.

    Precision is broken down into three dimensions: relevance, directness, and
    conciseness. Audio is sent alongside the question text so Gemini can
    judge how well the speaker answered.
    """

    async def evaluate_response(
        self,
        audio_bytes: bytes,
        mime_type: str,
        question_text: str,
        noise_level: str = "low",
    ) -> dict:
        """Evaluate the precision of an audio response.

        Args:
            audio_bytes: Raw audio data.
            mime_type: MIME type of the audio (e.g. "audio/webm").
            question_text: The question the student was answering.
            noise_level: Informational hint about background noise; reserved for
                future prompt tuning and not currently used in the prompt.

        Returns:
            Parsed dict with transcript, scores, feedback, strengths,
            improvement_areas, and audio_intelligible flag.

        Raises:
            PrecisionGeminiError: If the Gemini call fails for any reason.
        """
        try:
            return await self._call_gemini(audio_bytes, mime_type, question_text)
        except PrecisionGeminiError:
            raise
        except Exception as exc:
            raise PrecisionGeminiError(f"Gemini precision evaluation failed: {exc}") from exc

    async def _call_gemini(
        self, audio_bytes: bytes, mime_type: str, question_text: str
    ) -> dict:
        """Send audio and question to Gemini and return the structured evaluation.

        Args:
            audio_bytes: Raw audio data.
            mime_type: MIME type of the audio.
            question_text: The question text to embed in the prompt.

        Returns:
            Parsed response dict matching PRECISION_RESPONSE_SCHEMA.
        """
        client = genai.Client(api_key=settings.gemini_api_key)
        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        prompt_part = types.Part.from_text(text=_PROMPT_TEMPLATE.format(question=question_text))

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_part, prompt_part],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PRECISION_RESPONSE_SCHEMA,
            ),
        )
        return response.parsed
