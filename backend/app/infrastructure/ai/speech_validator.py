import json

from google import genai
from google.genai import types

from config import settings

SPEECH_VALIDATION_PROMPT = """Escucha este audio con atencion.

Responde dos preguntas de forma estricta y objetiva:
1. ¿El audio contiene una voz humana hablando en español? (has_speech)
2. ¿Lo que dice el hablante corresponde o se parece a esta frase: "{phrase_text}"? (matches_phrase)

Criterios estrictos:
- has_speech es false si hay silencio, ruido de fondo sin voz, o sonidos que no son habla humana.
- matches_phrase es false si el hablante dice palabras al azar, otro idioma, sonidos sin sentido, \
o algo claramente diferente a la frase indicada.
- matches_phrase solo puede ser true si has_speech es true.

Devuelve unicamente este JSON sin texto adicional:
{{"has_speech": <true o false>, "matches_phrase": <true o false>}}"""

VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "has_speech": {"type": "boolean"},
        "matches_phrase": {"type": "boolean"},
    },
    "required": ["has_speech", "matches_phrase"],
}

SILENCE_RESULT = {
    "has_speech": False,
    "matches_phrase": False,
}


class GeminiSpeechValidator:
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def validate(
        self,
        audio_bytes: bytes,
        mime_type: str,
        phrase_text: str,
    ) -> dict:
        prompt_text = SPEECH_VALIDATION_PROMPT.format(phrase_text=phrase_text)
        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        text_part = types.Part.from_text(text=prompt_text)

        try:
            response = await self._client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=[audio_part, text_part])],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=VALIDATION_SCHEMA,
                ),
            )
            return json.loads(response.text)
        except Exception:
            return SILENCE_RESULT
