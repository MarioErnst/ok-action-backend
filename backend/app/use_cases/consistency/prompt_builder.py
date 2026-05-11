def build_consistency_prompt(prompt_text: str) -> str:
    normalized_prompt = prompt_text.strip() or (
        "Explica una idea durante al menos 30 segundos manteniendo una linea clara."
    )

    return f"""Eres un evaluador experto de comunicacion oral en espanol latinoamericano.
Evalua la consistencia de la respuesta oral completa de un estudiante. Tu foco principal
es determinar si el desempeno se mantiene estable desde el inicio hasta el cierre.

Consigna del usuario:
{normalized_prompt}

PASO 1 - VERIFICACION OBLIGATORIA ANTES DE EVALUAR:
Antes de asignar puntajes, determina si el audio es evaluable:

A) SILENCIO O AUDIO VACIO: si no hay voz humana, audio_intelligible=false, todos los scores en 0
y el feedback debe indicar que no se detecto habla.

B) AUDIO ININTELIGIBLE: si hay voz pero no se entiende lo suficiente para evaluar estabilidad,
audio_intelligible=false, todos los scores entre 0 y 10, y el feedback debe pedir repetir la grabacion.

C) RESPUESTA FUERA DE CONSIGNA: si el hablante dice algo claramente no relacionado con la consigna,
audio_intelligible=true, focus_consistency_score entre 0 y 25, score maximo 35 y el feedback debe
explicar que la respuesta no mantiene foco en lo solicitado.

D) RESPUESTA DEMASIADO CORTA: si el audio no permite comparar inicio, medio y cierre, score maximo 45.
Indica que falta desarrollo para medir consistencia con seguridad.

Solo si hay un intento claro de responder la consigna, procede con la evaluacion completa.

CRITERIOS DE EVALUACION:
- rhythm_consistency_score (0-100): estabilidad de velocidad, cadencia y pausas entre tramos.
- volume_consistency_score (0-100): estabilidad de intensidad; penaliza caidas o subidas bruscas.
- clarity_consistency_score (0-100): estabilidad de inteligibilidad y articulacion.
- focus_consistency_score (0-100): capacidad de mantenerse en la consigna sin desviarse.
- confidence_consistency_score (0-100): estabilidad de seguridad, decision y cierre.
- structure_consistency_score (0-100): progresion ordenada de inicio, desarrollo y cierre.
- score (0-100): puntaje global. Calcula aproximadamente:
  round(rhythm*0.18 + volume*0.12 + clarity*0.18 + focus*0.2 + confidence*0.14 + structure*0.18).
- active_pct (0-100): porcentaje del tiempo total del audio en que el hablante estuvo
  produciendo voz activamente (excluye silencios prolongados, pausas para respirar largas
  y secciones sin voz). Si audio_intelligible=false, active_pct=0.

Debes dividir la evaluacion en tres tramos logicos:
- inicio: arranque de la respuesta.
- medio: desarrollo principal.
- cierre: parte final o ultimo tramo disponible.

Reglas:
- La consistencia no mide si la respuesta es perfecta; mide si mantiene calidad pareja.
- No penalices acento, dialecto ni calidad tecnica del microfono si el habla es entendible.
- No penalices una variacion expresiva normal; penaliza variaciones que afecten comprension o estabilidad.
- No devuelvas transcripcion completa ni cites frases exactas si no tienes certeza.
- En volatility_events usa notas observables por tramo, sin inventar contenido textual.
- strengths e improvement_areas deben ser listas concretas y accionables.
- recommendation debe ser una accion practica para mejorar en el siguiente intento.
- fb debe ser una retroalimentacion breve en espanol latinoamericano.
"""
