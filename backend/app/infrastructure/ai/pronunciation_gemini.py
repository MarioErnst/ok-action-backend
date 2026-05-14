# AI service for pronunciation. Full integration docs: documentacion/modulos/pronunciacion.md
import json

from google import genai
from google.genai import types

from config import settings

PRONUNCIATION_EVALUATION_PROMPT = """Eres un experto en fonetica clinica del espanol latinoamericano. \
Tu tarea es evaluar la pronunciacion de un hablante que lee en voz alta la siguiente frase:

FRASE: "{phrase_text}"
NIVEL DE DIFICULTAD: {level}

PASO 1 — VERIFICACION OBLIGATORIA ANTES DE EVALUAR:
Antes de asignar cualquier puntaje, determina si el audio es evaluable:

A) SILENCIO O AUDIO VACIO: Si el audio no contiene voz humana, solo ruido de fondo o silencio, \
todos los puntajes deben ser 0 y el feedback debe indicar "No se detectó habla en el audio. \
Por favor graba tu voz leyendo la frase en voz alta."

B) CONTENIDO INCORRECTO: Si el hablante dice algo que no corresponde a la frase indicada \
(palabras al azar, otro idioma, sonidos sin sentido, balbuceos), todos los puntajes deben ser \
entre 0 y 15 y el feedback debe indicar que el contenido no coincide con la frase evaluada.

C) FRASE INCOMPLETA: Si el hablante dice solo parte de la frase, los puntajes deben reflejar \
esa incompletitud (maximo 40) y el feedback debe señalarlo explicitamente.

Solo si el audio contiene un intento claro de leer la frase indicada, procede con la evaluacion completa:

1. PRODUCCION DE VOCALES: Verifica que las cinco vocales (/a/, /e/, /i/, /o/, /u/) se articulen \
con abertura y posicion correcta. Detecta vocales reducidas, centralizadas o sustituidas.

2. PRODUCCION DE CONSONANTES: Evalua la articulacion de cada consonante. Atencion especial a:
   - /r/ simple vs /rr/ vibrante multiple
   - /b/-/v/ fricativa bilabial
   - /s/ alveolar
   - /ll/ vs /y/ (yeismo)
   - /x/ fricativa velar (jota)
   - /d/ fricativa intervocalica vs oclusiva inicial

3. PUNTO Y MODO DE ARTICULACION: Verifica que cada fonema se produzca en el lugar correcto \
(bilabial, alveolar, palatal, velar) y con el modo correcto \
(oclusivo, fricativo, nasal, lateral, vibrante).

4. FLUIDEZ FONETICA: Evalua la transicion entre sonidos. Detecta bloqueos, repeticiones \
o sustituciones sistematicas.

5. INTELIGIBILIDAD: Mide si el habla es comprensible para un hablante nativo, \
incluso con variacion dialectal menor.

Devuelve un JSON con la siguiente estructura exacta:
{{
  "overall_score": <entero 0-100>,
  "vowel_score": <entero 0-100>,
  "consonant_score": <entero 0-100>,
  "fluency_score": <entero 0-100>,
  "intelligibility_score": <entero 0-100>,
  "feedback": "<retroalimentacion constructiva en espanol, minimo 2 oraciones>",
  "phoneme_errors": [
    {{
      "phoneme": "<fonema con error>",
      "word": "<palabra donde ocurre>",
      "actual_issue": "<descripcion del problema>",
      "suggestion": "<ejercicio o tecnica concreta>"
    }}
  ]
}}

Las puntuaciones deben ser estrictas y honestas. \
Solo devuelve el JSON, sin texto adicional."""

PRONUNCIATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer"},
        "vowel_score": {"type": "integer"},
        "consonant_score": {"type": "integer"},
        "fluency_score": {"type": "integer"},
        "intelligibility_score": {"type": "integer"},
        "feedback": {"type": "string"},
        "phoneme_errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phoneme": {"type": "string"},
                    "word": {"type": "string"},
                    "actual_issue": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["phoneme", "word", "actual_issue", "suggestion"],
            },
        },
    },
    "required": [
        "overall_score",
        "vowel_score",
        "consonant_score",
        "fluency_score",
        "intelligibility_score",
        "feedback",
        "phoneme_errors",
    ],
}


class GeminiPronunciationError(Exception):
    pass


class GeminiPronunciationService:
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def evaluate_phrase(
        self,
        audio_bytes: bytes,
        mime_type: str,
        phrase_text: str,
        level: str,
    ) -> dict:
        prompt_text = PRONUNCIATION_EVALUATION_PROMPT.format(
            phrase_text=phrase_text,
            level=level,
        )

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        text_part = types.Part.from_text(text=prompt_text)

        try:
            response = await self._client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=[audio_part, text_part])],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PRONUNCIATION_RESPONSE_SCHEMA,
                    # Phonetic scoring + phoneme_errors list is a detection
                    # task. Low temperature keeps the same input scoring
                    # consistently and reduces hallucinated phoneme errors.
                    temperature=0.2,
                ),
            )
        except Exception as error:
            raise GeminiPronunciationError(
                f"Error al comunicarse con Gemini: {error}"
            ) from error

        raw_text = response.text
        if not raw_text:
            raise GeminiPronunciationError("Gemini devolvio una respuesta vacia")

        try:
            evaluation = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise GeminiPronunciationError(
                f"Gemini devolvio una respuesta con formato invalido: {error}"
            ) from error

        return evaluation
