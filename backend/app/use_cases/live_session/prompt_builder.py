_DIM_ANALYSIS_SECTIONS = {
    "pron": (
        "- PRONUNCIACION: Evalua vocales (/a/, /e/, /i/, /o/, /u/), consonantes "
        "(especialmente /r/, /rr/, /b/, /v/, /s/, /ll/, /y/, /j/, /d/ intervocalica), "
        "fluidez fonetica e inteligibilidad."
    ),
    "acc": (
        "- ACENTUACION: Evalua el acento prosodico (palabras agudas, graves, "
        "esdrujulas, sobreesdrujulas), curva de entonacion (declarativa, interrogativa, "
        "exclamativa) y ritmo entre grupos fonicos."
    ),
    "mul": (
        "- MULETILLAS: Detecta palabras o expresiones de relleno: "
        "'o sea', 'este', 'eh', 'um', 'ah', 'basicamente', 'literalmente', "
        "'como que', 'la verdad', 'de hecho', 'pues', 'bueno', y cualquier "
        "patron repetitivo sin valor semantico. "
        "Para cada muletilla detectada incluye en 'ctx' un fragmento breve (maximo 10 palabras) "
        "de la transcripcion que muestre el contexto donde aparecio."
    ),
}


def build_system_prompt(selected_dims: list[str]) -> str:
    """
    Builds the Gemini prompt for a live session audio analysis cycle.
    Only includes instructions for the selected dimensions.

    Args:
        selected_dims: List of dimension keys to include. Valid values: "pron", "acc", "mul".

    Returns:
        A formatted prompt string with analysis instructions for the requested dimensions.
    """
    analysis_sections = "\n".join(
        _DIM_ANALYSIS_SECTIONS[dim] for dim in selected_dims if dim in _DIM_ANALYSIS_SECTIONS
    )

    return f"""Eres un asistente especializado en analisis de habla en espanol latinoamericano. \
Analiza el siguiente segmento de audio segun estas dimensiones:

{analysis_sections}

Reglas:
- Si el audio es silencio o ruido sin habla, todos los scores deben ser 0.
- Las puntuaciones son estrictas y honestas (0-100).
- El campo "fb" es una sola oracion breve y constructiva en espanol.
"""
