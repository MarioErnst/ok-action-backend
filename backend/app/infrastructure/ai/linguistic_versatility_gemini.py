# Gemini-based evaluator of linguistic versatility (lexical diversity, synonym
# usage, vocabulary richness) for Spanish oral responses.
# Full docs: documentacion/modulos/versatilidad-linguistica.md
from google import genai
from google.genai import types

from config import settings


# Schema enforces the exact shape Gemini must return; pairs with
# response_mime_type="application/json" so the response is always parseable.
VERSATILITY_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=[
        "versatility_score",
        "vocabulary_richness",
        "feedback",
        "audio_intelligible",
    ],
    properties={
        # Whole-number 0-100 because the frontend renders it as a percentage.
        "versatility_score": types.Schema(type=types.Type.INTEGER),
        # 1=básico, 2=intermedio, 3=avanzado. Numeric so analytics queries can
        # average it across sessions without parsing strings.
        "vocabulary_richness": types.Schema(type=types.Type.INTEGER),
        "feedback": types.Schema(type=types.Type.STRING),
        "audio_intelligible": types.Schema(type=types.Type.BOOLEAN),
    },
)


_GUIDED_PROMPT_TEMPLATE = """\
Eres un evaluador de versatilidad lingüística en español rioplatense. Se le hizo la siguiente pregunta al estudiante y te paso el audio con su respuesta:

"{question}"

Evaluá la versatilidad lingüística de la respuesta:

versatility_score (0-100):
- Mide la variedad léxica: ¿el estudiante repite las mismas palabras o usa sinónimos y variantes?
- 100 = vocabulario muy variado, casi sin repeticiones de palabras de contenido (sustantivos, verbos, adjetivos).
- 50 = repite varias palabras de contenido pero también usa sinónimos.
- 0 = repite las mismas palabras todo el tiempo, vocabulario muy pobre.
- Ignorá repeticiones de palabras de función (artículos, pronombres, conectores básicos como "y", "que", "de").
- Penalizá repeticiones de muletillas léxicas (la misma palabra de contenido usada 3+ veces si tiene alternativas claras).

vocabulary_richness (1, 2 o 3):
- 1 = básico: usa solo palabras frecuentes y comunes del lenguaje cotidiano.
- 2 = intermedio: combina palabras comunes con algunas más específicas, técnicas o menos frecuentes.
- 3 = avanzado: usa vocabulario rico, variado, con palabras precisas, técnicas o de registro elevado.

feedback:
- 1 o 2 oraciones en español, concretas y útiles.
- Si versatility_score es alto, destacá una virtud específica observada.
- Si es bajo, mencioná 1 palabra que se repitió y sugerí 1 sinónimo concreto.
- No usés frases genéricas tipo "buen trabajo" o "podés mejorar". Sé específico.

IMPORTANTE:
- NO penalices por ruido de fondo ni calidad de audio.
- Si el audio es ininteligible o la persona no habló, audio_intelligible=false y versatility_score=0, vocabulary_richness=1, feedback="No se pudo procesar el audio."
- Si pudiste evaluar el habla, audio_intelligible=true.
- Escribí el feedback en español rioplatense (vos, no tú).
"""


_FREE_PROMPT_TEMPLATE = """\
Eres un evaluador de versatilidad lingüística en español rioplatense. Te paso el audio de un estudiante hablando libremente sobre el tema que eligió.

Evaluá la versatilidad lingüística del discurso completo:

versatility_score (0-100):
- Mide la variedad léxica: ¿el estudiante repite las mismas palabras o usa sinónimos y variantes?
- 100 = vocabulario muy variado, casi sin repeticiones de palabras de contenido.
- 50 = repite varias palabras de contenido pero también usa sinónimos.
- 0 = repite las mismas palabras todo el tiempo.
- Ignorá repeticiones de palabras de función (artículos, pronombres, conectores básicos).
- Penalizá repeticiones de palabras de contenido cuando hay alternativas claras.

vocabulary_richness (1, 2 o 3):
- 1 = básico, 2 = intermedio, 3 = avanzado (palabras precisas, técnicas o de registro elevado).

feedback:
- 1 o 2 oraciones en español, concretas. Si bajó la versatilidad, mencioná una palabra que se repitió y un sinónimo. Si fue alta, destacá una virtud específica.
- Sin frases genéricas. En español rioplatense (vos, no tú).

IMPORTANTE:
- NO penalices por ruido de fondo ni calidad de audio.
- Si el audio es ininteligible, audio_intelligible=false, scores neutrales y feedback="No se pudo procesar el audio."
"""


class VersatilityGeminiError(Exception):
    """Raised when the Gemini versatility call fails."""


class GeminiVersatilityService:
    """Evaluates lexical versatility of a spoken response using the Gemini API.

    Gemini receives the audio multimodally (no separate transcription step) and
    returns a structured JSON with score, richness level (1-3), feedback, and
    an intelligibility flag.
    """

    async def evaluate_response(
        self,
        audio_bytes: bytes,
        mime_type: str,
        question_text: str,
    ) -> dict:
        """Evaluate one guided answer.

        Args:
            audio_bytes: Raw audio bytes from the client.
            mime_type: MIME type of the audio (e.g. "audio/mp4", "audio/webm").
            question_text: The question the student was answering.

        Returns:
            dict matching VERSATILITY_RESPONSE_SCHEMA.

        Raises:
            VersatilityGeminiError: If the Gemini call fails.
        """
        try:
            return await self._call(
                audio_bytes,
                mime_type,
                _GUIDED_PROMPT_TEMPLATE.format(question=question_text),
            )
        except Exception as exc:
            raise VersatilityGeminiError(
                f"Gemini versatility evaluation failed: {exc}"
            ) from exc

    async def evaluate_free(
        self,
        audio_bytes: bytes,
        mime_type: str,
    ) -> dict:
        """Evaluate a free-mode session (single audio, no question).

        Args:
            audio_bytes: Raw audio bytes from the client.
            mime_type: MIME type of the audio.

        Returns:
            dict matching VERSATILITY_RESPONSE_SCHEMA.

        Raises:
            VersatilityGeminiError: If the Gemini call fails.
        """
        try:
            return await self._call(audio_bytes, mime_type, _FREE_PROMPT_TEMPLATE)
        except Exception as exc:
            raise VersatilityGeminiError(
                f"Gemini versatility evaluation failed: {exc}"
            ) from exc

    async def _call(self, audio_bytes: bytes, mime_type: str, prompt: str) -> dict:
        client = genai.Client(api_key=settings.gemini_api_key)
        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        prompt_part = types.Part.from_text(text=prompt)

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_part, prompt_part],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VERSATILITY_RESPONSE_SCHEMA,
            ),
        )
        return response.parsed
