"""Gemini Flash-Lite contextual classifier for ambiguous filler words.

The dictionary matcher in `muletillas_dictionary` flags any token from
the unigram set, but some of those tokens (`tipo`, `este`, `esta`,
`esto`, `pues`) double as real Spanish content words. Sending every
match straight to the user as a strike produces false positives like
"ningún tipo de muletillas" — `tipo` here is a noun.

This module wraps a Gemini 2.5 Flash-Lite call (text-only, no audio)
that takes the transcript plus the ambiguous candidates and returns
the subset that the model considers real fillers in context. The
supervisor only emits a strike for those.

Why this model: Flash-Lite is the cheapest and fastest text-only
Gemini variant (~250-400 ms median for short prompts), which keeps
the corten total latency under ~1.5 s end-to-end. The task is a
short, well-bounded classification — accuracy on it is essentially
the same as Flash.

Why text-only: the supervisor already has the transcript from
AssemblyAI; sending audio here would double the request size and
slow the call without adding information the LLM does not already
have in the transcript.

Failure mode: if the call fails or times out, callers should treat
every ambiguous candidate as a false positive (drop them). That keeps
the corten precision-first — better to miss a real "tipo" filler than
to interrupt the user for "ningún tipo de".
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from google import genai
from google.genai import types

from config import settings


logger = logging.getLogger(__name__)


# Pinned Flash-Lite model id per CLAUDE.md rule against *-latest
# aliases. Update when bumping to a newer Flash-Lite revision.
_MODEL = "gemini-2.5-flash-lite"


# Low temperature: the task is classification, not generation. We want
# the same verdict for the same transcript on every call.
_TEMPERATURE = 0.0


_CLASSIFIER_PROMPT = """Eres un revisor de muletillas en español (Latinoamérica).

Te paso un fragmento literal y una lista de palabras candidatas con sus posiciones.
Para cada candidata, decidí si en ese contexto está usada como MULETILLA (relleno verbal
sin contenido, hesitación, conector vacío) o como PALABRA NORMAL (sustantivo, verbo,
adverbio, conector con contenido real).

Reglas:
- "tipo" es muletilla cuando funciona como conector vacío ("y tipo, no sé").
  NO es muletilla cuando es sustantivo o adjetivo ("un tipo raro", "ningún tipo de X").
- "este/esta/esto" son muletilla cuando aparecen aislados como relleno ("este, lo que pasa...").
  NO son muletilla cuando son demostrativos ("este auto", "esta semana").
- "pues" es muletilla cuando es relleno conversacional ("pues, no sé").
  NO es muletilla cuando introduce explicación causal real ("pues bien", "pues que").

Devolvé un JSON con la lista exacta de índices (0-based) de las candidatas que SÍ son
muletillas en este contexto. Si ninguna es muletilla devolvé una lista vacía.

FRAGMENTO:
{transcript}

CANDIDATAS:
{candidates}
"""


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "filler_indices": {
            "type": "array",
            "items": {"type": "integer"},
        },
    },
    "required": ["filler_indices"],
}


@dataclass(frozen=True)
class AmbiguousCandidate:
    """One ambiguous match the classifier needs to confirm.

    `index` is the position inside the caller's input list; the model
    returns the indices it considers real fillers so the caller can
    map back to its own data. `word` is the canonical filler form.
    `context_snippet` is the surrounding fragment the classifier reads
    to decide.
    """

    index: int
    word: str
    context_snippet: str


class MuletillaContextClassifierError(Exception):
    """Raised when Gemini fails or returns a malformed answer."""


class MuletillaContextClassifier:
    """Gemini Flash-Lite client that confirms ambiguous filler matches."""

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def classify(
        self,
        transcript: str,
        candidates: list[AmbiguousCandidate],
    ) -> set[int]:
        """Return the set of candidate indices the model confirms as fillers.

        Raises MuletillaContextClassifierError on any failure so the
        caller can decide the fallback (today: drop all ambiguous
        matches, precision-first).
        """

        if not candidates:
            return set()

        candidate_lines = "\n".join(
            f"{c.index}. word={c.word!r} contexto={c.context_snippet!r}"
            for c in candidates
        )
        prompt_text = _CLASSIFIER_PROMPT.format(
            transcript=transcript,
            candidates=candidate_lines,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=_MODEL,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt_text)],
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                    temperature=_TEMPERATURE,
                ),
            )
        except Exception as error:
            raise MuletillaContextClassifierError(
                f"Error al llamar al clasificador: {error}"
            ) from error

        raw_text = response.text
        if not raw_text:
            raise MuletillaContextClassifierError(
                "El clasificador devolvió una respuesta vacía"
            )

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise MuletillaContextClassifierError(
                f"Respuesta del clasificador con JSON inválido: {error}"
            ) from error

        indices = payload.get("filler_indices")
        if not isinstance(indices, list):
            raise MuletillaContextClassifierError(
                "Respuesta del clasificador sin 'filler_indices' válido"
            )

        confirmed: set[int] = set()
        valid_indices = {c.index for c in candidates}
        for raw in indices:
            if isinstance(raw, int) and raw in valid_indices:
                confirmed.add(raw)
        return confirmed
