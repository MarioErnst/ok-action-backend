_DIM_ANALYSIS_SECTIONS = {
    "precision": (
        "- PRECISION: Evalua la respuesta a la pregunta recibida. "
        "relevance (0-100): ¿Respondio la pregunta directamente? "
        "directness (0-100): ¿Llego al punto sin rodeos? "
        "conciseness (0-100): ¿Fue conciso sin repetir ideas? "
        "overall = round(relevance*0.4 + directness*0.3 + conciseness*0.3). "
        "Si el audio es ininteligible, audio_intelligible=false y todos los scores en 0."
    ),
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
    "fluency": (
        "- FLUIDEZ: Evalua continuidad del habla espontanea. Detecta bloqueos, trabas, "
        "repeticiones inmediatas, reinicios de frase y pausas largas que cortan una idea. "
        "No penalices muletillas leves ni pausas naturales si no rompen la continuidad. "
        "Estima palabras por minuto (wpm), ritmo, coherencia local y entrega una nota accionable. "
        "Para cada traba relevante incluye en 'det' un objeto con w=palabra o fragmento, "
        "n=ocurrencias y ctx=contexto breve."
    ),
}


def build_system_prompt(selected_dims: list[str]) -> str:
    """
    Builds the Gemini prompt for a live session audio analysis cycle.
    Only includes instructions for the selected dimensions.

    Args:
        selected_dims: List of dimension keys to include. Valid values: "pron", "acc", "mul", "precision", "fluency".

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
