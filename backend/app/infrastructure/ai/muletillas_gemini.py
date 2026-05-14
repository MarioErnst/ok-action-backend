# AI service for muletillas. Full integration docs: documentacion/modulos/muletillas.md
import json

from google import genai
from google.genai import types

from config import settings

MULETILLAS_EVALUATION_PROMPT = """Eres un experto en comunicacion oral en espanol latinoamericano. \
Tu tarea es analizar la respuesta oral de un estudiante a la siguiente pregunta y detectar \
el uso de muletillas (palabras de relleno que interrumpen la fluidez del discurso).

PREGUNTA HECHA AL ESTUDIANTE: "{question_text}"

PASO 1 - VERIFICACION OBLIGATORIA ANTES DE EVALUAR:
Antes de asignar cualquier puntaje, determina si el audio es evaluable:

A) SILENCIO O AUDIO VACIO: Si el audio no contiene voz humana, todos los puntajes deben ser 0, \
total_muletillas_count debe ser 0, muletillas_per_minute debe ser 0 y el feedback debe indicar \
"No se detecto habla en el audio. Por favor graba tu voz respondiendo la pregunta."

B) CONTENIDO NO RELACIONADO: Si el hablante dice algo completamente fuera de contexto, \
todos los puntajes deben ser entre 0 y 20 y el feedback debe indicarlo.

Solo si el audio contiene un intento claro de responder la pregunta, procede con la evaluacion completa:

MULETILLAS A DETECTAR (no exhaustivo, detecta cualquier palabra de relleno):
- "o sea", "este", "eh", "um", "ah", "basicamente", "literalmente", "obviamente"
- "la verdad", "o sea que", "de hecho", "como que", "en fin", "pues", "bueno"
- Repeticiones de palabras sin sentido semantico
- Cualquier otro patron de relleno recurrente en el audio

CRITERIOS DE EVALUACION:
- overall_score (0-100): Calidad general de comunicacion
- fluency_score (0-100): Fluidez del discurso, pausas naturales vs rellenas
- muletillas_score (0-100): Claridad libre de muletillas (100 = ninguna muletilla)
- Severidad por muletilla: "high" si aparece 3 o mas veces, "medium" si 2 veces, "low" si 1 vez
- muletillas_per_minute: estima duracion del audio y calcula frecuencia

TRANSCRIPCION:
Ademas de las metricas, devuelve la transcripcion exacta de lo que dijo el hablante en el campo \
`transcript`, y un arreglo `muletillas_positions` con la posicion de cada ocurrencia de muletilla \
dentro de esa transcripcion. La posicion se expresa como un indice 0-based de carácter inicial y \
final (`start_char` inclusivo, `end_char` exclusivo) dentro de `transcript`. Es decir, \
`transcript[start_char:end_char]` debe devolver exactamente la muletilla original.

Si el hablante usa la misma muletilla N veces, debe aparecer N entradas en `muletillas_positions`, \
una por ocurrencia, en el orden en que se dicen.

Devuelve un JSON con la siguiente estructura exacta:
{{
  "overall_score": <numero 0-100>,
  "fluency_score": <numero 0-100>,
  "muletillas_score": <numero 0-100>,
  "total_muletillas_count": <entero>,
  "muletillas_per_minute": <numero decimal>,
  "muletillas_detected": [
    {{
      "word": "<muletilla detectada>",
      "count": <entero>,
      "severity": "<low|medium|high>",
      "suggestion": "<sugerencia concreta y accionable en espanol>"
    }}
  ],
  "transcript": "<texto exacto del hablante, en espanol>",
  "muletillas_positions": [
    {{
      "word": "<muletilla exacta tal como aparece en transcript>",
      "start_char": <entero 0-based, inclusivo>,
      "end_char": <entero 0-based, exclusivo>
    }}
  ],
  "feedback": "<retroalimentacion general constructiva, minimo 2 oraciones>",
  "strengths": "<aspectos positivos de la comunicacion>",
  "improvement_areas": "<areas concretas de mejora>"
}}

Solo devuelve el JSON, sin texto adicional."""

MULETILLAS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer"},
        "fluency_score": {"type": "integer"},
        "muletillas_score": {"type": "integer"},
        "total_muletillas_count": {"type": "integer"},
        "muletillas_per_minute": {"type": "number"},
        "muletillas_detected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "count": {"type": "integer"},
                    "severity": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["word", "count", "severity", "suggestion"],
            },
        },
        "transcript": {"type": "string"},
        "muletillas_positions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "start_char": {"type": "integer"},
                    "end_char": {"type": "integer"},
                },
                "required": ["word", "start_char", "end_char"],
            },
        },
        "feedback": {"type": "string"},
        "strengths": {"type": "string"},
        "improvement_areas": {"type": "string"},
    },
    "required": [
        "overall_score",
        "fluency_score",
        "muletillas_score",
        "total_muletillas_count",
        "muletillas_per_minute",
        "muletillas_detected",
        "transcript",
        "muletillas_positions",
        "feedback",
        "strengths",
        "improvement_areas",
    ],
}


class GeminiMuletillasError(Exception):
    pass


class GeminiMuletillasService:
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def evaluate_response(
        self,
        audio_bytes: bytes,
        mime_type: str,
        question_text: str,
    ) -> dict:
        prompt_text = MULETILLAS_EVALUATION_PROMPT.format(question_text=question_text)

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        text_part = types.Part.from_text(text=prompt_text)

        try:
            response = await self._client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=[audio_part, text_part])],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MULETILLAS_RESPONSE_SCHEMA,
                    # Detection-heavy task: keep the temperature low so two
                    # runs of the same audio return the same muletillas list.
                    temperature=0.2,
                ),
            )
        except Exception as error:
            raise GeminiMuletillasError(
                f"Error al comunicarse con Gemini: {error}"
            ) from error

        raw_text = response.text
        if not raw_text:
            raise GeminiMuletillasError("Gemini devolvio una respuesta vacia")

        try:
            evaluation = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise GeminiMuletillasError(
                f"Gemini devolvio una respuesta con formato invalido: {error}"
            ) from error

        return evaluation
