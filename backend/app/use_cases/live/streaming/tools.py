"""Function tool declarations for the live streaming evaluator.

Each tool corresponds to one evaluation module the supervisor cares about
during a live session. Gemini Live receives this set at WS connect time
and is instructed (via the system prompt) to call exactly one tool when
it perceives the corresponding error, otherwise stay silent.

Design notes:

- transcript_snippet is REQUIRED on every tool. It is the anti-
  hallucination contract: the model must echo back the words it heard
  immediately before the error. The supervisor drops any tool call
  whose snippet is empty so a model that fires a tool with no audio
  evidence cannot cut the session.

- severity is REQUIRED for the three modules. The supervisor maps every
  severity (low/medium/high) to a single strike per call. The strike
  threshold lives in the supervisor, not here, so this module stays a
  pure declaration registry.

- The registry below maps LiveStreamModule -> tool declaration so
  adding a new module is a one-line change: append a new entry. The
  supervisor consumes build_tools_for_modules() to assemble the live
  config; this keeps the live WS payload exactly proportional to what
  the client selected.

This module imports nothing from the genai SDK so the rest of the code
base can construct tool payloads without forcing a SDK import. The
supervisor adapts the dicts into genai types when calling live.connect.
"""

from __future__ import annotations

from typing import Literal


LiveStreamModule = Literal["muletillas", "pronunciation", "accentuation"]


VALID_LIVE_STREAM_MODULES: tuple[LiveStreamModule, ...] = (
    "muletillas",
    "pronunciation",
    "accentuation",
)


_MULETILLA_TOOL = {
    "name": "flag_muletilla",
    "description": (
        "Reporta una muletilla que el usuario acaba de pronunciar en su "
        "habla espontanea en espanol latinoamericano. Llama esta funcion "
        "EXACTAMENTE una vez por cada ocurrencia individual. Solo reporta "
        "muletillas que escuchaste literalmente en el audio reciente "
        "(eh, este, o sea, mmm, ah). No reportes palabras frecuentes "
        "como 'la verdad' o 'de hecho' salvo que sean usadas como "
        "muletilla real."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "word": {
                "type": "string",
                "description": "La muletilla exacta tal como sono (ej. 'eh', 'este').",
            },
            "transcript_snippet": {
                "type": "string",
                "description": (
                    "Fragmento de transcripcion (5 a 12 palabras) que rodea "
                    "la muletilla y que efectivamente escuchaste. Sirve como "
                    "evidencia y contrato anti-alucinacion."
                ),
            },
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": (
                    "Severidad de la muletilla: low si es la primera de su "
                    "tipo en la sesion, medium si se repite, high si "
                    "interrumpe el hilo discursivo."
                ),
            },
        },
        "required": ["word", "transcript_snippet", "severity"],
    },
}


_PRONUNCIATION_TOOL = {
    "name": "flag_pronunciation_error",
    "description": (
        "Reporta un error fonemico perceptible que el usuario acaba de "
        "cometer en espanol latinoamericano. Llama esta funcion una vez "
        "por error individual. Errores tipicos: /rr/ debil, confusion "
        "/b/-/v/, /s/ aspirada o ceceada, /ll/-/y/ confundidas, /d/ "
        "final caida, vocales nasalizadas. Solo reporta lo que "
        "escuchaste; no asumas nada del resto del discurso."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "word": {
                "type": "string",
                "description": "Palabra donde ocurrio el error fonemico.",
            },
            "phoneme": {
                "type": "string",
                "description": "Fonema afectado (ej. 'rr', 's', 'll', 'd').",
            },
            "actual_issue": {
                "type": "string",
                "description": "Una linea describiendo como se pronuncio (en espanol).",
            },
            "suggestion": {
                "type": "string",
                "description": "Una linea con la indicacion accionable (en espanol).",
            },
            "transcript_snippet": {
                "type": "string",
                "description": (
                    "Fragmento de transcripcion (5 a 12 palabras) que rodea "
                    "la palabra erronea. Evidencia anti-alucinacion."
                ),
            },
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Severidad percibida del error fonemico.",
            },
        },
        "required": [
            "word",
            "phoneme",
            "actual_issue",
            "suggestion",
            "transcript_snippet",
            "severity",
        ],
    },
}


_ACCENTUATION_TOOL = {
    "name": "flag_accentuation_error",
    "description": (
        "Reporta un error prosodico perceptible en una palabra que el "
        "usuario acaba de decir en espanol latinoamericano (acento "
        "desplazado, entonacion no natural, ritmo cortado). Llama esta "
        "funcion una vez por palabra con error. Solo reporta lo que "
        "escuchaste."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "word": {
                "type": "string",
                "description": "Palabra donde ocurrio el error prosodico.",
            },
            "expected_stress": {
                "type": "string",
                "description": (
                    "Como debio acentuarse (ej. 'PA-ja-ro' con la silaba "
                    "tonica en mayusculas)."
                ),
            },
            "actual_issue": {
                "type": "string",
                "description": "Una linea describiendo como la pronuncio (en espanol).",
            },
            "suggestion": {
                "type": "string",
                "description": "Una linea con la indicacion accionable (en espanol).",
            },
            "transcript_snippet": {
                "type": "string",
                "description": (
                    "Fragmento de transcripcion (5 a 12 palabras) que rodea "
                    "la palabra. Evidencia anti-alucinacion."
                ),
            },
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Severidad percibida del error prosodico.",
            },
        },
        "required": [
            "word",
            "expected_stress",
            "actual_issue",
            "suggestion",
            "transcript_snippet",
            "severity",
        ],
    },
}


_TOOL_BY_MODULE: dict[LiveStreamModule, dict] = {
    "muletillas": _MULETILLA_TOOL,
    "pronunciation": _PRONUNCIATION_TOOL,
    "accentuation": _ACCENTUATION_TOOL,
}


# Reverse lookup so the supervisor can map a tool call name back to the
# module category it belongs to without re-parsing tool definitions. New
# modules add one entry here and stay consistent across the codebase.
TOOL_NAME_TO_MODULE: dict[str, LiveStreamModule] = {
    _MULETILLA_TOOL["name"]: "muletillas",
    _PRONUNCIATION_TOOL["name"]: "pronunciation",
    _ACCENTUATION_TOOL["name"]: "accentuation",
}


def build_tools_for_modules(modules: list[LiveStreamModule]) -> list[dict]:
    """Return Gemini Live function_declarations for the requested modules.

    Caller orders the modules; we preserve VALID_LIVE_STREAM_MODULES
    order in the output so the system prompt and the tool list stay
    aligned for prompt-engineering inspection.

    Raises ValueError when modules is empty or contains an unknown name.
    """

    if not modules:
        raise ValueError("At least one module must be selected for live streaming")

    invalid = [m for m in modules if m not in VALID_LIVE_STREAM_MODULES]
    if invalid:
        raise ValueError(f"Invalid live streaming module(s): {invalid}")

    ordered_unique: list[LiveStreamModule] = [
        m for m in VALID_LIVE_STREAM_MODULES if m in modules
    ]
    return [_TOOL_BY_MODULE[m] for m in ordered_unique]
