"""System prompt builder for the Gemini Live streaming evaluator.

The supervisor sends this prompt as the system_instruction when it
opens the live WS session. The prompt has three hard constraints:

1. The model must be SILENT. response_modalities is set to TEXT in the
   session config, but the prompt reinforces it so the model does not
   produce verbal acknowledgements either.

2. The model must call EXACTLY ONE TOOL per detected error. No
   summaries, no commentary, no greetings. If nothing wrong is heard,
   the model produces no output at all.

3. Every tool call must include a transcript_snippet that quotes the
   audio just heard. The supervisor enforces this filter; the prompt
   tells the model that calls without a real snippet are wasted.

The prompt is built per-session from the list of modules the client
selected, so the model only sees the tools that are actually wired up.
"""

from __future__ import annotations

from app.use_cases.live.streaming.tools import (
    LiveStreamModule,
    VALID_LIVE_STREAM_MODULES,
)


_HEADER = """Eres un evaluador silencioso de comunicacion oral en espanol latinoamericano.
Estas escuchando el audio en vivo de un estudiante que habla espontaneamente
durante una sesion de practica.

TU UNICA SALIDA SON LLAMADAS A FUNCIONES (tool calls). No hables. No saludes.
No emitas ni una palabra en texto ni en audio. Si no detectas ningun error
en el audio reciente, mantente en silencio."""


_TOOL_CALL_RULES = """REGLAS GENERALES PARA LLAMAR A LAS HERRAMIENTAS:

A) Llama la herramienta EN EL MOMENTO en que escuchas el error, no esperes
   al final de la frase. Cada milisegundo cuenta para el alumno.

B) Llama UNA herramienta por error individual. Si escuchas dos muletillas
   distintas seguidas, llama flag_muletilla dos veces.

C) En cada llamada, transcript_snippet DEBE contener entre 5 y 12 palabras
   que realmente escuchaste en el audio reciente. Esto es un contrato
   anti-alucinacion: si el snippet esta vacio o no corresponde al audio,
   la llamada sera ignorada por el sistema.

D) NO infieras errores que no escuchaste. NO reportes errores en palabras
   que el estudiante no haya dicho. Solo lo que efectivamente paso por el
   microfono.

E) NO produzcas texto explicativo ni audio. Si llegaste hasta aca y no
   tienes nada que reportar, simplemente sigue escuchando."""


_MULETILLAS_SECTION = """MODULO MULETILLAS (herramienta flag_muletilla):
Reporta muletillas espontaneas en espanol latinoamericano:
"eh", "este", "o sea", "mmm", "ah", "bueno" (cuando es muletilla),
"viste", "tipo". Solo lo que escuchaste literalmente. NO reportes
expresiones legitimas que el estudiante use con sentido."""


_PRONUNCIATION_SECTION = """MODULO PRONUNCIACION (herramienta flag_pronunciation_error):
Reporta errores fonemicos perceptibles: /rr/ debil, confusion /b/-/v/,
/s/ aspirada o ceceada, /ll/-/y/ confundidas, /d/ final caida, vocales
nasalizadas, transiciones cortadas. Solo lo que escuchaste."""


_ACCENTUATION_SECTION = """MODULO ACENTUACION (herramienta flag_accentuation_error):
Reporta errores prosodicos perceptibles en palabras concretas: acento
desplazado, entonacion no natural, ritmo cortado. Da expected_stress
con la silaba tonica esperada en mayusculas (ej. 'PA-ja-ro')."""


_SECTION_BY_MODULE: dict[LiveStreamModule, str] = {
    "muletillas": _MULETILLAS_SECTION,
    "pronunciation": _PRONUNCIATION_SECTION,
    "accentuation": _ACCENTUATION_SECTION,
}


_CLOSING = """RECUERDA: tu unica forma de comunicarte es llamando a las
herramientas. Cualquier texto o audio que produzcas sera descartado por el
sistema y no llegara al estudiante. Mantente alerta y silencioso."""


def build_live_streaming_prompt(modules: list[LiveStreamModule]) -> str:
    """Compose the system_instruction for a live streaming session.

    Output is plain text suitable for genai's system_instruction field.
    Sections appear in the canonical module order regardless of input
    order so prompt diffs stay stable across sessions.
    """

    if not modules:
        raise ValueError("At least one module must be selected for live streaming")

    invalid = [m for m in modules if m not in VALID_LIVE_STREAM_MODULES]
    if invalid:
        raise ValueError(f"Invalid live streaming module(s): {invalid}")

    ordered_unique: list[LiveStreamModule] = [
        m for m in VALID_LIVE_STREAM_MODULES if m in modules
    ]

    parts: list[str] = [_HEADER, _TOOL_CALL_RULES, "DETECCIONES SOLICITADAS:"]
    for module in ordered_unique:
        parts.append(_SECTION_BY_MODULE[module])
    parts.append(_CLOSING)

    return "\n\n".join(parts)
