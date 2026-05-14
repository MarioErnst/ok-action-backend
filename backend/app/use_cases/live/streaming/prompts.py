"""Frame-evaluation prompt builder for live sessions.

A frame is a 5-8 second audio fragment cut from an ongoing live session.
Gemini receives the fragment alongside this prompt and returns a small
JSON response with one section per requested module plus an
evaluated_until_seconds field. The client uses that response to feed
the strike counter and decide whether to stop the user.

Differences relative to composed (end-of-session) prompts:
- Tells Gemini that the audio is a fragment of a longer ongoing session
  and that it should evaluate only complete utterances (up to the last
  complete sentence it heard) — anything trailing will appear again in
  the next frame thanks to the client-side overlap.
- Asks for evaluated_until_seconds so the client knows what portion of
  the fragment was actually evaluated.
- No feedback strings. The client does not surface text during the
  session; the rich post-session feedback comes from the composed call.
- More lenient audio gate: short or noisy fragments produce neutral 50
  scores rather than 0/error, so a single tough frame does not poison
  the strike count.
"""

from __future__ import annotations

from typing import Literal


FrameModule = Literal["muletillas", "accentuation", "pronunciation"]


VALID_FRAME_MODULES: tuple[FrameModule, ...] = (
    "muletillas",
    "accentuation",
    "pronunciation",
)


_HEADER = """Eres un evaluador experto de comunicacion oral en espanol latinoamericano.
Estas evaluando un FRAGMENTO corto (entre 5 y 8 segundos) de una sesion de practica
de habla libre que sigue en curso. El estudiante continuara hablando despues del
fragmento. No bases la evaluacion en lo que falta; evalua solo lo que escuchaste."""


_FRAME_INSTRUCTIONS = """REGLAS PARA EVALUAR EL FRAGMENTO:

A) Evalua solo hasta la ULTIMA ORACION COMPLETA que escuchaste. Si el fragmento
termina a mitad de palabra o frase, ignora ese pedazo final: aparecera otra vez
en el siguiente fragmento gracias a un solapamiento que ya viene dado.

B) Reporta en el campo "evaluated_until_seconds" del JSON raiz, como entero, el
segundo (relativo al inicio del fragmento) hasta el que evaluaste. Si evaluaste el
fragmento entero, devuelve la duracion total redondeada hacia abajo.

C) Si el fragmento es muy corto, muy silencioso o ininteligible, devuelve scores
50 (neutro) y listas "detected" vacias. NO devuelvas scores 0 salvo que haya
silencio absoluto en todo el fragmento.

D) Las sugerencias accionables (campos `suggestion`, `expected_stress`,
`actual_issue`) deben ser breves (una linea, en espanol latinoamericano). Estos
no son feedback libre: son indicaciones puntuales para cada error detectado y se
muestran al usuario inmediatamente cuando el fragmento es evaluado."""


_FRAME_TRANSCRIPT_REQUIREMENT = """REGLA ANTI-ALUCINACION PARA EL FRAGMENTO:
Antes de evaluar cualquier modulo, transcribe palabra por palabra lo que escuchaste
en el fragmento y devuelvelo en el campo `transcript` del JSON raiz. Usa minusculas
y puntuacion natural. Si no estas seguro de una palabra, escribe lo mas cercano que
oiste o usa [inaudible].

ESTA TRANSCRIPCION ES UN CONTRATO. Cada item anclado que reportes (muletilla,
error fonemico, error prosodico) DEBE referirse a una palabra o segmento que
aparezca literalmente en `transcript`. Si la palabra no aparece en `transcript`,
NO puedes reportarla. Prefiere reportar menos antes que inventar."""


_FRAME_MULETILLAS_SECTION = """MODULO MULETILLAS:
Detecta muletillas que aparezcan LITERALMENTE en `transcript`. Ejemplos clasicos
a considerar SOLO si estan en transcript: "eh", "este", "o sea". NO reportes
otras muletillas habituales ("la verdad", "de hecho", "obviamente", "basicamente",
etc.) salvo que tu transcripcion las contenga textualmente.

Severidad por palabra unica en el fragmento:
- "high" si aparece 3 o mas veces
- "medium" si aparece 2 veces
- "low" si aparece 1 vez

Devuelve en la seccion "muletillas":
- total (entero): cantidad total de ocurrencias detectadas en el fragmento.
- detected: lista de objetos {word, count, severity, timestamp_ms} donde
  timestamp_ms es el milisegundo relativo al inicio del fragmento en que
  aparece la primera ocurrencia de esa palabra. Si no detectaste muletillas,
  devuelve detected: [] y total: 0.
- muletillas_positions: lista con una entrada por cada ocurrencia individual
  de muletilla, ordenadas como aparecen en `transcript`. Cada entrada es
  {word, start_char, end_char} donde `transcript[start_char:end_char]` DEBE
  devolver exactamente la muletilla (start_char inclusivo, end_char exclusivo,
  indices 0-based)."""


_FRAME_ACCENTUATION_SECTION = """MODULO ACENTUACION:
Evalua la calidad prosodica del fragmento sobre lo que el estudiante produjo.
No hay frase target; analiza el patron acentual de las palabras producidas, la
naturalidad de la curva melodica y el ritmo, comparado contra un hablante
nativo de espanol latinoamericano.

Devuelve en la seccion "accentuation":
- pronunciation_score (entero 0-100): claridad articulatoria en el fragmento.
- rhythm_score (entero 0-100): cadencia y ritmo en el fragmento.
- intonation_score (entero 0-100): variacion tonal en el fragmento.
- stress_score (entero 0-100): correccion de acentos prosodicos en las palabras.
- prosodic_errors: lista con UNA entrada por palabra del fragmento con un
  error prosodico perceptible. Cada entrada es {word, expected_stress,
  actual_issue, suggestion} donde:
    * word: la palabra del transcript donde ocurrio el error. DEBE
      aparecer literalmente en `transcript`; esa restriccion sigue firme
      como contrato anti-alucinacion.
    * expected_stress: como debio acentuarse (ej. "PA-ja-ro" con la silaba
      tonica en mayusculas, o una indicacion breve de la curva esperada).
    * actual_issue: una linea describiendo como la pronuncio el estudiante.
    * suggestion: una linea con la indicacion accionable.
  IMPORTANTE: la sesion en vivo necesita feedback granular. Si percibis
  CUALQUIER acento desplazado o entonacion no natural en una palabra del
  transcript, repORTalo, aunque la severidad sea leve. Es mejor reportar
  varios errores percibidos que ninguno. Solo se omite cuando la palabra
  no aparece en el transcript. Si verdaderamente la prosodia es nativa,
  devolve prosodic_errors: []."""


_FRAME_PRONUNCIATION_SECTION = """MODULO PRONUNCIACION:
Evalua la calidad fonetica del fragmento. Observa vocales (apertura,
posicion), consonantes (especialmente /r/-/rr/, /b/-/v/, /s/, /ll/-/y/),
transiciones entre sonidos, y la inteligibilidad general para un hablante
nativo de espanol latinoamericano.

Devuelve en la seccion "pronunciation":
- vowel_score (entero 0-100): calidad de vocales en el fragmento.
- consonant_score (entero 0-100): calidad de consonantes en el fragmento.
- fluency_score (entero 0-100): fluidez fonetica y transiciones.
- intelligibility_score (entero 0-100): inteligibilidad general.
- phoneme_errors: lista con UNA entrada por palabra del fragmento con un
  error fonemico perceptible. Cada entrada es {phoneme, word, actual_issue,
  suggestion} donde:
    * phoneme: el fonema afectado (ej. "rr", "s", "ll", "d").
    * word: la palabra del transcript donde ocurrio el error. DEBE
      aparecer literalmente en `transcript`; esa restriccion sigue firme
      como contrato anti-alucinacion.
    * actual_issue: una linea describiendo el problema observado.
    * suggestion: una linea con la indicacion accionable.
  IMPORTANTE: la sesion en vivo necesita feedback granular. Si percibis
  CUALQUIER fonema mal articulado, debil o sustituido en una palabra del
  transcript, repORTalo, aunque la severidad sea leve. Errores tipicos en
  espanol latinoamericano que valen la pena reportar: /rr/ debil, /b/-/v/
  sin distincion, /s/ aspirada o ceceada, /ll/-/y/ confundidas, /d/ final
  caida, vocales nasalizadas. Es mejor reportar varios errores percibidos
  que ninguno. Solo se omite cuando la palabra no aparece en el transcript.
  Si verdaderamente todo sono nativo, devolve phoneme_errors: []."""


_SECTION_BY_MODULE: dict[FrameModule, str] = {
    "muletillas": _FRAME_MULETILLAS_SECTION,
    "accentuation": _FRAME_ACCENTUATION_SECTION,
    "pronunciation": _FRAME_PRONUNCIATION_SECTION,
}


_CLOSING = """Devuelve EXCLUSIVAMENTE un JSON valido conforme al schema entregado, sin
texto adicional. No incluyas secciones de modulos que no se solicitaron."""


def build_frame_prompt(
    modules: list[FrameModule],
    evaluated_so_far_seconds: int | None = None,
) -> str:
    """Build the per-frame Gemini prompt.

    evaluated_so_far_seconds is the position of this frame inside the
    larger session (seconds from the session start). Including it in the
    prompt is purely informational so Gemini can frame the evaluation
    pedagogically (e.g. "we are at second 42 of the session"); it does
    not affect scoring.
    """

    if not modules:
        raise ValueError("At least one module must be selected for frame evaluation")

    invalid = [m for m in modules if m not in VALID_FRAME_MODULES]
    if invalid:
        raise ValueError(f"Invalid module(s): {invalid}")

    ordered_unique: list[FrameModule] = [m for m in VALID_FRAME_MODULES if m in modules]

    parts: list[str] = [_HEADER, _FRAME_INSTRUCTIONS, _FRAME_TRANSCRIPT_REQUIREMENT]

    if evaluated_so_far_seconds is not None and evaluated_so_far_seconds >= 0:
        parts.append(
            f"CONTEXTO: este fragmento empieza en el segundo {evaluated_so_far_seconds} de la sesion."
        )

    parts.append("EVALUACION POR MODULO:")
    for module in ordered_unique:
        parts.append(_SECTION_BY_MODULE[module])

    parts.append(_CLOSING)

    return "\n\n".join(parts)
