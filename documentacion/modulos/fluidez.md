# Módulo de Fluidez — Backend

## 1. Descripción funcional

El módulo de Fluidez evalúa la continuidad del habla de un usuario mientras responde una consigna. Su foco principal es detectar disrupciones del flujo verbal: bloqueos, repeticiones, reinicios de frase, pausas largas que cortan ideas y ritmo poco natural.

La evaluación también verifica concordancia con la consigna. Esto evita marcar como buen intento una respuesta fluida pero fuera de tema. La fluidez se evalúa como calidad comunicativa del intento, no solo como velocidad al hablar.

El sistema entrega feedback en tiempo real mediante WebSocket. Cuando detecta problemas relevantes, envía advertencias visuales al frontend sin cortar inmediatamente la grabación.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| **Router** | `backend/app/presentation/routers/fluency.py` | Gestiona el WebSocket `/fluency/session`, autenticación, buffer de audio y ciclo de análisis. |
| **Prompt Builder** | `backend/app/use_cases/fluency/prompt_builder.py` | Construye instrucciones para Gemini incluyendo consigna, verificaciones previas y criterios de evaluación. |
| **Session Manager** | `backend/app/use_cases/fluency/session_manager.py` | Mantiene estado en memoria, calcula promedio y decide cuándo emitir advertencias. |
| **Servicio IA** | `backend/app/infrastructure/ai/fluency_gemini.py` | Envía audio PCM a Gemini y exige una respuesta JSON estructurada. |
| **Tests** | `backend/tests/test_fluency.py` | Cubre prompt y reglas de advertencia. |

## 3. Modelo de datos

Actualmente Fluidez no persiste sesiones en PostgreSQL. El estado vive en memoria durante la conexión WebSocket.

Al finalizar, el backend envía `average_score` al cliente, pero no guarda historial. Si se agrega persistencia futura, debería crearse una tabla propia para intentos de fluidez en lugar de mezclarla con `live_sessions`.

## 4. Esquemas de solicitud y respuesta

### Inicio de sesión

Mensaje cliente → servidor:

```json
{
  "type": "start",
  "prompt_text": "Describe una experiencia en la que tuviste que explicar una idea compleja."
}
```

### Análisis de segmento

Mensaje servidor → cliente:

```json
{
  "type": "analysis",
  "data": {
    "audio_intelligible": true,
    "score": 84,
    "fluency_score": 86,
    "continuity_score": 82,
    "rhythm_score": 80,
    "prompt_alignment_score": 90,
    "coherence_score": 84,
    "classification": "fluidez_buena",
    "stuck_events": [
      {"word": "migración", "count": 2, "ctx": "la migración, migración de datos"}
    ],
    "repetitions": 1,
    "restarts": 0,
    "long_blocks": 0,
    "wpm": 124,
    "pace_feedback": "Ritmo estable, con una pausa natural antes de la idea principal.",
    "strengths": ["Mantiene una idea central clara", "Ritmo comprensible"],
    "improvement_areas": ["Evitar repetir palabras al iniciar una explicación"],
    "fb": "La respuesta mantiene buena continuidad y responde la consigna. Cuida las repeticiones al introducir conceptos importantes."
  }
}
```

### Advertencia

Mensaje servidor → cliente:

```json
{
  "type": "warning",
  "reason": "not_aligned_with_prompt",
  "data": { "...": "analysis" }
}
```

Razones posibles:

| Reason | Descripción |
|--------|-------------|
| `audio_not_intelligible` | Hay voz, pero no se entiende suficiente para evaluar. |
| `not_aligned_with_prompt` | La respuesta no concuerda con la consigna. |
| `low_fluency_score` | El score global baja de 70. |
| `fluency_blocks_detected` | Hay 3 o más eventos negativos en el segmento. |
| `time_limit` | La sesión llegó al máximo de 120 segundos. |

## 5. Casos de uso

### `build_fluency_prompt(prompt_text)`

Normaliza la consigna y construye un prompt con verificación previa obligatoria:

1. silencio o audio vacío;
2. audio ininteligible;
3. respuesta fuera de consigna;
4. respuesta demasiado corta;
5. evaluación completa solo si hay un intento claro.

El prompt separa métricas de fluidez, continuidad, ritmo, concordancia con la consigna y coherencia. Esto replica el patrón robusto de módulos como Precisión: primero valida si el audio se puede evaluar y luego asigna puntajes.

### `analyze_fluency_audio_segment(audio_bytes, prompt)`

Envía audio PCM 16 kHz a Gemini con `response_mime_type="application/json"` y un schema cerrado. Retorna `None` si el segmento es demasiado corto, si Gemini falla o si la respuesta no puede parsearse.

Mientras no exista una capa Speech-to-Text dedicada, el módulo no muestra transcripción completa al usuario. Gemini puede estimar eventos y contexto breve, pero no se usa como fuente autoritativa de texto exacto.

### `FluencySessionState.evaluate_attention(analysis)`

Acumula el análisis y decide si debe emitirse una advertencia:

1. `audio_intelligible=false` → `audio_not_intelligible`;
2. tiempo máximo alcanzado → `time_limit`;
3. `prompt_alignment_score < 70` → `not_aligned_with_prompt`;
4. `score < 70` → `low_fluency_score`;
5. eventos negativos acumulados del segmento ≥ 3 → `fluency_blocks_detected`.

## 6. Integración con Gemini AI

**Modelo:** `gemini-2.5-flash`

**Entrada:** audio PCM 16 kHz mono y prompt de texto con la consigna.

**Criterios principales:**

- no penalizar acento, dialecto ni calidad técnica si el habla es entendible;
- no confundir muletillas leves con problemas de fluidez;
- penalizar pausas solo cuando cortan la idea;
- evaluar concordancia con la consigna para detectar respuestas fuera de tema;
- devolver feedback accionable, fortalezas y áreas de mejora.

## 7. Endpoints de la API

### WS `/fluency/session`

Establece una sesión WebSocket de práctica de fluidez.

- **Autenticación:** token JWT en query param `?token=...`
- **Inicio:** mensaje JSON `{"type":"start","prompt_text":"..."}`
- **Audio:** frames binarios PCM 16 kHz mono
- **Salida:** mensajes `ready`, `analysis`, `warning` y `session_ended`

## 8. Integración con Sesión Libre

Fluidez también puede seleccionarse como dimensión `"fluency"` en `/live/session`.

En ese modo:

1. El frontend incluye `"fluency"` dentro de `dims`.
2. `live_session.py` valida la dimensión en `VALID_DIMS`.
3. `prompt_builder.py` agrega una sección de análisis de fluidez para habla espontánea.
4. `live_gemini.py` exige `dims.fluency` con score, clasificación, WPM, repeticiones, reinicios, bloqueos, feedback de ritmo y eventos detectados.
5. El resultado se guarda dentro de `live_sessions.analyses`, no en una tabla propia.

La diferencia principal es que el módulo standalone tiene consigna y puede medir `prompt_alignment_score`; sesión libre no tiene consigna fija, por lo que evalúa continuidad del habla espontánea.
