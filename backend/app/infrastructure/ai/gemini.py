# AI service for accentuation. Full integration docs: documentacion/modulos/acentuacion.md
import json

from google import genai
from google.genai import types

from config import settings

ACCENTUATION_EVALUATION_PROMPT = """Eres un experto en fonetica y prosodia del espanol latinoamericano. \
Tu tarea es evaluar la acentuacion de un hablante que lee en voz alta la siguiente frase:

FRASE: "{phrase_text}"

PASO 1 — VERIFICACION OBLIGATORIA ANTES DE EVALUAR:
Antes de asignar cualquier puntaje, determina si el audio es evaluable:

A) SILENCIO O AUDIO VACIO: Si el audio no contiene voz humana, solo ruido de fondo o silencio, \
todos los puntajes deben ser 0 y el feedback debe indicar "No se detectó habla en el audio. \
Por favor graba tu voz leyendo la frase en voz alta."

B) CONTENIDO INCORRECTO: Si el hablante dice algo que no corresponde a la frase indicada \
(palabras al azar, otro idioma, sonidos sin sentido), todos los puntajes deben ser entre 0 y 15 \
y el feedback debe indicar que el contenido no coincide con la frase evaluada.

C) FRASE INCOMPLETA: Si el hablante dice solo parte de la frase, los puntajes deben reflejar \
esa incompletitud (maximo 40) y el feedback debe señalarlo.

Solo si el audio contiene un intento claro de leer la frase indicada, procede con la evaluacion completa:

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
  "stress_score": <numero entero 0-100>,
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

Las puntuaciones deben ser estrictas y honestas. Solo devuelve el JSON, sin texto adicional."""

GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer"},
        "pronunciation_score": {"type": "integer"},
        "rhythm_score": {"type": "integer"},
        "intonation_score": {"type": "integer"},
        "stress_score": {"type": "integer"},
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
        "stress_score",
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
