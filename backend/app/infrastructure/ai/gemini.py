import json

from google import genai
from google.genai import types

from config import settings

ACCENTUATION_EVALUATION_PROMPT = """Eres un experto en fonetica y prosodia del espanol latinoamericano. \
Tu tarea es evaluar la acentuacion de un hablante que lee en voz alta la siguiente frase:

FRASE: "{phrase_text}"

Analiza el audio proporcionado y evalua los siguientes aspectos:

1. ACENTO PROSODICO: Verifica que el hablante coloque correctamente el acento tonico en cada palabra. \
Identifica palabras agudas, graves, esdrujulas y sobreesdrujulas y si el patron acentual fue respetado.

2. PATRONES SILABICOS: Evalua si la division silabica y el peso silabico son naturales y correctos.

3. CURVA DE ENTONACION: Analiza si la melodia de la frase es apropiada para el tipo de oracion \
(declarativa, interrogativa, exclamativa). Verifica que los ascensos y descensos tonales sean naturales.

4. RITMO: Evalua la cadencia general, las pausas entre grupos fonicos, y si el tempo es adecuado \
para una lectura natural.

5. CLARIDAD: Evalua la nitidez articulatoria general y si las vocales y consonantes se producen \
con precision.

Devuelve un JSON con la siguiente estructura exacta:
{{
  "overall_score": <numero entero 0-100>,
  "pronunciation_score": <numero entero 0-100>,
  "rhythm_score": <numero entero 0-100>,
  "intonation_score": <numero entero 0-100>,
  "stress_accuracy_score": <numero entero 0-100>,
  "feedback": "<texto en espanol con retroalimentacion constructiva y especifica, minimo 2 oraciones>",
  "specific_errors": [
    {{
      "word": "<palabra con error>",
      "expected_stress": "<descripcion del acento esperado>",
      "actual_issue": "<descripcion del problema detectado>",
      "suggestion": "<sugerencia concreta de mejora>"
    }}
  ]
}}

Si no detectas errores significativos, devuelve una lista vacia en specific_errors y un feedback positivo.
Las puntuaciones deben ser justas y constructivas. Un hablante nativo promedio sin formacion fonetica \
deberia obtener entre 70-85. Solo devuelve el JSON, sin texto adicional."""

GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "number"},
        "pronunciation_score": {"type": "number"},
        "rhythm_score": {"type": "number"},
        "intonation_score": {"type": "number"},
        "stress_accuracy_score": {"type": "number"},
        "feedback": {"type": "string"},
        "specific_errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "expected_stress": {"type": "string"},
                    "actual_issue": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["word", "expected_stress", "actual_issue", "suggestion"],
            },
        },
    },
    "required": [
        "overall_score",
        "pronunciation_score",
        "rhythm_score",
        "intonation_score",
        "stress_accuracy_score",
        "feedback",
        "specific_errors",
    ],
}


class GeminiEvaluationError(Exception):
    pass


class GeminiAccentuationService:
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def evaluate_phrase(
        self,
        audio_bytes: bytes,
        mime_type: str,
        phrase_text: str,
    ) -> dict:
        prompt_text = ACCENTUATION_EVALUATION_PROMPT.format(phrase_text=phrase_text)

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        text_part = types.Part.from_text(text=prompt_text)

        try:
            response = await self._client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=[audio_part, text_part])],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GEMINI_RESPONSE_SCHEMA,
                ),
            )
        except Exception as error:
            raise GeminiEvaluationError(
                f"Error al comunicarse con Gemini: {error}"
            ) from error

        raw_text = response.text
        if not raw_text:
            raise GeminiEvaluationError("Gemini devolvio una respuesta vacia")

        try:
            evaluation = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise GeminiEvaluationError(
                f"Gemini devolvio una respuesta con formato invalido: {error}"
            ) from error

        return evaluation
