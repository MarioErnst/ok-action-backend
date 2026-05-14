"""Composed Gemini prompt builder for live audio evaluation.

The standalone prompts of the audio composable modules (muletillas,
accentuation, pronunciation) assume specific input shapes: muletillas
expects a question_text, accentuation/pronunciation expect a phrase_text
being read aloud. Live session is always free speech, so we cannot reuse
those prompts as-is. Instead we build a single prompt that contains a
shared free-speech intro and one section per audio module selected.

Facial expression is also a composable module from the client's
perspective, but Gemini does not evaluate it from the audio. The
facial summary is computed in the browser from the emotion classifier
and submitted to the finalize endpoint, where persist_composed_evaluation
handles it separately. This module is therefore intentionally absent
from the prompt body and the response schema.
"""

from __future__ import annotations

from typing import Literal


ComposableModule = Literal[
    "muletillas",
    "accentuation",
    "pronunciation",
    "facial_expression",
]


VALID_MODULES: tuple[ComposableModule, ...] = (
    "muletillas",
    "accentuation",
    "pronunciation",
    "facial_expression",
)


# Modules whose evaluation comes back from Gemini's text response.
# facial_expression is excluded because its data comes from the client.
_GEMINI_EVALUATED_MODULES: tuple[ComposableModule, ...] = (
    "muletillas",
    "accentuation",
    "pronunciation",
)


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

ESTA TRANSCRIPCION ES UN CONTRATO. Cada modulo que reporte items anclados (muletillas,
errores fonemicos, errores prosodicos) DEBE referirse a palabras o segmentos que
aparezcan literalmente en `transcript`. Si una palabra no aparece en `transcript`, NO
puedes reportarla como muletilla, error fonemico ni error prosodico. Prefiere reportar
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


_ACCENTUATION_SECTION = """MODULO ACENTUACION:
Evalua la calidad prosodica general del habla libre. Como no hay frase target,
analiza el patron acentual sobre las palabras que el estudiante produce: si las
silabas tonicas estan correctamente marcadas, si la curva melodica es natural,
si el ritmo de las pausas y grupos foneticos suena fluido para un hablante
nativo de espanol latinoamericano.

Devuelve en la seccion "accentuation" del JSON:
- pronunciation_score (entero 0-100): claridad articulatoria general.
- rhythm_score (entero 0-100): cadencia y ritmo natural del habla.
- intonation_score (entero 0-100): variacion tonal y curva melodica.
- stress_score (entero 0-100): correccion de los acentos prosodicos en las palabras producidas.
- feedback (string en espanol): retroalimentacion concreta sobre acentuacion en habla libre, minimo 2 oraciones."""


_PRONUNCIATION_SECTION = """MODULO PRONUNCIACION:
Evalua la calidad fonetica general del habla libre. Sin frase target, observa la
produccion de vocales (apertura, posicion), consonantes (especialmente /r/-/rr/,
/b/-/v/, /s/, /ll/-/y/, /x/, /d/), transiciones entre sonidos, y la
inteligibilidad general del estudiante.

Devuelve en la seccion "pronunciation" del JSON:
- vowel_score (entero 0-100): calidad de produccion de vocales.
- consonant_score (entero 0-100): calidad de produccion de consonantes.
- fluency_score (entero 0-100): fluidez fonetica y transiciones entre sonidos.
- intelligibility_score (entero 0-100): inteligibilidad general para un hablante nativo.
- feedback (string en espanol): retroalimentacion concreta sobre pronunciacion, minimo 2 oraciones."""


_SECTION_BY_MODULE: dict[ComposableModule, str] = {
    "muletillas": _MULETILLAS_SECTION,
    "accentuation": _ACCENTUATION_SECTION,
    "pronunciation": _PRONUNCIATION_SECTION,
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
    the input list, so equivalent inputs produce identical prompts. This makes
    prompt caching (if Gemini ever supports it for this content) deterministic
    and makes the prompt easier to inspect in logs.

    Modules not present in _SECTION_BY_MODULE (currently just
    facial_expression) are silently skipped at the prompt level: they are
    valid composables but their data does not come from Gemini.
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
        # Caller asked only for facial_expression (or nothing prompt-shaped).
        # We still need a sane prompt for Gemini to gate audio intelligibility
        # against, so we ask only for audio_intelligible without any module section.
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
