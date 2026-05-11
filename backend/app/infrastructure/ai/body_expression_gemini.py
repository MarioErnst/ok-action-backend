from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

_FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "improvements": {"type": "array", "items": {"type": "string"}},
        "recommendation": {"type": "string"},
    },
    "required": ["summary", "strengths", "improvements", "recommendation"],
}


async def generate_body_expression_feedback(prompt: str, metrics: dict[str, object]) -> dict | None:
    client = genai.Client(api_key=settings.gemini_api_key)
    text = (
        "Actua como coach de comunicacion oral y lenguaje corporal. "
        "No inventes transcripcion, palabras ni acciones no observadas: solo usa las metricas agregadas. "
        "Devuelve feedback breve en espanol chileno/neutro, accionable y respetuoso.\n\n"
        f"Consigna del usuario: {prompt or 'No informada'}\n"
        f"Metricas agregadas JSON: {json.dumps(metrics, ensure_ascii=False)}\n\n"
        "Interpreta postura, apertura, gesticulacion, estabilidad, energia y encuadre. "
        "Si una metrica es baja, explica el patron observable probable sin afirmar detalles de video."
    )

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=text)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_FEEDBACK_SCHEMA,
            ),
        )
    except Exception as exc:
        logger.warning("Gemini body expression feedback failed: %s", exc)
        return None

    if not response.text:
        return None

    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "JSON decode error from Gemini body expression: %s | raw: %.200s",
            exc,
            response.text,
        )
        return None
