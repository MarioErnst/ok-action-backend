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
        "patron repetitivo sin valor semantico."
    ),
}

_DIM_RESPONSE_KEYS = {
    "pron": '"pron":{"sc":<0-100>,"err":[{"ph":"<fonema>","w":"<palabra>","fix":"<sugerencia breve>"}]}',
    "acc": '"acc":{"sc":<0-100>,"err":[{"w":"<palabra>","exp":"<acento esperado>","act":"<lo detectado>"}]}',
    "mul": '"mul":{"sc":<0-100>,"det":[{"w":"<muletilla>","n":<conteo>}]}',
}


def build_system_prompt(selected_dims: list[str]) -> str:
    """
    Builds the Gemini system prompt for a live session.
    Only includes instructions for the selected dimensions.

    Args:
        selected_dims: List of dimension keys to include. Valid values: "pron", "acc", "mul".

    Returns:
        A formatted system prompt string with analysis instructions and response format
        restricted to the requested dimensions.
    """
    analysis_sections = "\n".join(
        _DIM_ANALYSIS_SECTIONS[dim] for dim in selected_dims if dim in _DIM_ANALYSIS_SECTIONS
    )
    response_keys = ", ".join(
        _DIM_RESPONSE_KEYS[dim] for dim in selected_dims if dim in _DIM_RESPONSE_KEYS
    )

    return f"""Eres un asistente especializado en analisis de habla en espanol latinoamericano. \
El usuario esta hablando libremente. Despues de cada segmento de habla, analiza unicamente \
las siguientes dimensiones:

{analysis_sections}

FORMATO DE RESPUESTA OBLIGATORIO:
Responde UNICAMENTE con el siguiente bloque. Sin texto antes ni despues.

[EVAL]{{"dims":{{{response_keys}}},"overall":<0-100>,"fb":"<1 oracion de retroalimentacion en espanol>"}}[/EVAL]

Reglas:
- Si el audio es silencio o ruido, todos los scores deben ser 0.
- Las puntuaciones son estrictas y honestas (0-100).
- "fb" es una sola oracion breve y constructiva en espanol.
- Solo incluye las claves de dimensiones listadas arriba, no agregues otras.
"""
