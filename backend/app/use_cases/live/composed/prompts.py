"""Composed Gemini prompt builder for live audio evaluation.

The composable modules in a live session today are: muletillas (the
only one Gemini evaluates from the audio), facial_expression (data
comes from the browser emotion classifier), phonation and loudness
(data comes from a browser AudioWorklet that measures pitch/dB).
Pronunciation and accentuation were removed from the live composable
set in favor of phonation+loudness, which run client-side with
predictable cost and latency. Both pron/acc remain available as
standalone modules with their own pages.

Live session is always free speech, so we cannot reuse the standalone
muletillas prompt that assumes a question_text. Instead this module
builds a single prompt that contains the audio gate, the transcript
contract and the muletillas section.
"""

from __future__ import annotations

from typing import Literal


ComposableModule = Literal[
    "muletillas",
    "facial_expression",
    "phonation",
    "loudness",
]


VALID_MODULES: tuple[ComposableModule, ...] = (
    "muletillas",
    "facial_expression",
    "phonation",
    "loudness",
)


# Modules whose evaluation comes back from Gemini's text response.
# facial_expression, phonation and loudness are excluded because their
# data is produced 100% in the browser and submitted alongside the
# audio in the composed evaluation request.
_GEMINI_EVALUATED_MODULES: tuple[ComposableModule, ...] = ("muletillas",)


# Public alias used by the router to decide whether to invoke Gemini at
# all. If a request only selects client-side modules there is nothing
# the audio model can contribute and the endpoint short-circuits the call.
AUDIO_COMPOSABLE_MODULES: tuple[ComposableModule, ...] = _GEMINI_EVALUATED_MODULES


_HEADER = """Eres un evaluador experto de comunicacion oral en espanol latinoamericano.
Estas evaluando un audio de HABLA LIBRE de un estudiante en una sesion de practica.
El estudiante NO esta leyendo una frase fija; esta hablando espontaneamente sobre un
tema. Tu evaluacion debe basarse exclusivamente en lo que el estudiante produce, sin
asumir un texto target."""


_AUDIO_GATE = """PASO 1 - VERIFICACION OBLIGATORIA ANTES DE EVALUAR:
Antes de asignar puntajes, determina si el audio es evaluable y reporta el resultado
en el campo audio_intelligible del JSON raiz.

A) SILENCIO O AUDIO VACIO: si no hay voz humana, audio_intelligible=false. Todos los
scores numericos de cada modulo evaluado deben ser 0 y los feedback deben indicar
que no se detecto habla.

B) AUDIO ININTELIGIBLE: si hay voz pero no se entiende lo suficiente para evaluar,
audio_intelligible=false. Todos los scores entre 0 y 10 y los feedback deben pedir
repetir la grabacion.

C) DURACION MUY CORTA: si el audio es muy breve para una evaluacion confiable,
audio_intelligible=true pero los scores no deben superar 45 y el feedback debe
mencionar que falta desarrollo.

Solo si hay un intento claro de habla libre con duracion suficiente, procede con
la evaluacion completa de cada modulo seleccionado."""


_TRANSCRIPT_REQUIREMENT = """PASO 2 - TRANSCRIPCION LITERAL (REGLA ANTI-ALUCINACION):
Antes de evaluar cualquier modulo, transcribe palabra por palabra lo que el estudiante
dice en el audio y devuelvelo en el campo `transcript` del JSON raiz. Usa minusculas y
puntuacion natural. Si no estas seguro de una palabra, escribe lo que sonó mas cercano
o usa [inaudible].

ESTA TRANSCRIPCION ES UN CONTRATO. Cada muletilla reportada DEBE referirse a una
palabra o segmento que aparezca literalmente en `transcript`. Si una palabra no
aparece en `transcript`, NO puedes reportarla como muletilla. Prefiere reportar
menos antes que inventar."""


_CONSIGNA_TEMPLATE = """CONSIGNA DEL USUARIO PARA LA SESION:
{consigna}

Tenla en cuenta solo como contexto del tema; no penalices ni premies adherencia
literal a la consigna."""


_MULETILLAS_SECTION = """MODULO MULETILLAS:
Detecta palabras de relleno (muletillas) que aparezcan LITERALMENTE en `transcript`.
Ejemplos clasicos a considerar SOLO si estan en el transcript: "eh", "este", "o sea".
NO reportes muletillas tipicas ("la verdad", "de hecho", "obviamente", "basicamente",
etc.) salvo que tu transcripcion las contenga textualmente.

Severidad por palabra (basada en ocurrencias en el transcript):
- "high" si aparece 3 o mas veces
- "medium" si aparece 2 veces
- "low" si aparece 1 vez

Devuelve en la seccion "muletillas" del JSON:
- fluency_score (entero 0-100): fluidez global del discurso, descontando muletillas y rellenos.
- total_muletillas (entero): cantidad total de ocurrencias de muletillas en el transcript.
- detected: lista de objetos {word, count, severity, suggestion} con cada muletilla unica.
- muletillas_positions: lista con una entrada por cada ocurrencia individual de muletilla,
  ordenadas como aparecen en el transcript. Cada entrada es {word, start_char, end_char}
  donde `transcript[start_char:end_char]` DEBE devolver exactamente la muletilla
  (start_char inclusivo, end_char exclusivo, indices 0-based sobre el campo `transcript`).
  Si una muletilla aparece N veces, debe haber N entradas en muletillas_positions.
- feedback (string en espanol): retroalimentacion breve y constructiva, minimo 2 oraciones."""


_SECTION_BY_MODULE: dict[ComposableModule, str] = {
    "muletillas": _MULETILLAS_SECTION,
}


_CLOSING = """Devuelve EXCLUSIVAMENTE un JSON valido conforme al schema entregado, sin texto
adicional ni envoltorios. No agregues secciones de modulos que no se solicitaron."""


def build_composed_prompt(
    modules: list[ComposableModule],
    prompt_text: str | None = None,
) -> str:
    """Build a single Gemini prompt containing a section per selected
    audio module.

    The order of sections in the prompt follows VALID_MODULES, not the order of
    the input list, so equivalent inputs produce identical prompts.

    Modules not present in _SECTION_BY_MODULE (facial_expression,
    phonation, loudness today) are silently skipped at the prompt level:
    they are valid composables but their data does not come from Gemini.
    """

    if not modules:
        raise ValueError("At least one module must be selected for live evaluation")

    invalid = [m for m in modules if m not in VALID_MODULES]
    if invalid:
        raise ValueError(f"Invalid module(s): {invalid}")

    audio_modules: list[ComposableModule] = [
        m for m in VALID_MODULES if m in modules and m in _SECTION_BY_MODULE
    ]

    if not audio_modules:
        # Caller asked only for client-side modules. We still need a
        # sane prompt for Gemini to gate audio intelligibility against,
        # so we ask only for audio_intelligible without any module section.
        # Transcript is also unnecessary when no audio module needs anchoring.
        parts: list[str] = [
            _HEADER,
            _AUDIO_GATE,
            "PASO 2 - No se solicitaron modulos evaluables por audio en esta corrida.",
            _CLOSING,
        ]
        return "\n\n".join(parts)

    parts = [_HEADER, _AUDIO_GATE, _TRANSCRIPT_REQUIREMENT]

    consigna = (prompt_text or "").strip()
    if consigna:
        parts.append(_CONSIGNA_TEMPLATE.format(consigna=consigna))

    parts.append("PASO 3 - EVALUACION POR MODULO:")
    for module in audio_modules:
        parts.append(_SECTION_BY_MODULE[module])

    parts.append(_CLOSING)

    return "\n\n".join(parts)
