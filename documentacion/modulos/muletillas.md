# Muletillas — Documentación Backend

## 1. Descripción funcional

El módulo de Muletillas ayuda a los usuarios a identificar y reducir palabras de relleno (muletillas) en su comunicación oral. El flujo operativo es el siguiente:

1. El sistema presenta una pregunta aleatoria al usuario para estimular respuestas espontáneas.
2. El usuario graba su respuesta en voz alta.
3. Gemini AI transcribe el audio y analiza su contenido.
4. El sistema identifica muletillas (palabras de relleno como "eh", "um", "o sea", "este", etc.).
5. Se calcula la frecuencia y severidad de cada muletilla detectada.
6. La sesión completa se persiste en la base de datos para seguimiento del progreso.
7. El usuario recibe retroalimentación detallada: puntuaciones, muletillas identificadas, sugerencias de mejora, fortalezas y áreas de mejora.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| **Presentación (Router)** | `backend/app/presentation/routers/muletillas.py` | Recibe solicitudes HTTP, valida entrada, retorna respuestas. |
| **Presentación (Schemas)** | `backend/app/presentation/schemas/muletillas.py` | Define estructuras de solicitud y respuesta con validación. |
| **Casos de uso** | `backend/app/use_cases/muletillas/` | Lógica de negocio: preguntas, evaluación y persistencia (sessions.py, evaluate_response.py). |
| **Entidades** | `backend/app/domain/entities/muletillas_session.py` | Modelos `MuletillasSession` y `PhraseMuletillas`. |
| **Servicio IA** | `backend/app/infrastructure/ai/muletillas_gemini.py` | `GeminiMuletillasService`: análisis de audio con Gemini. |

## 3. Modelo de datos

### Tabla: `muletillas_sessions`

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la sesión. |
| `user_id` | UUID | FK → users (CASCADE) | Usuario propietario. |
| `question_text` | TEXT | NOT NULL | Pregunta presentada al usuario. |
| `overall_score` | NUMERIC(4,2) | NOT NULL | Puntuación general (0-100). |
| `fluency_score` | NUMERIC(4,2) | NOT NULL | Puntuación de fluidez (0-100). |
| `muletillas_score` | NUMERIC(4,2) | NOT NULL | Puntuación de ausencia de muletillas (0-100). |
| `total_muletillas_count` | INTEGER | NOT NULL | Número total de muletillas detectadas. |
| `muletillas_per_minute` | NUMERIC(5,2) | NOT NULL | Frecuencia de muletillas por minuto. |
| `feedback` | TEXT | NOT NULL | Retroalimentación general. |
| `strengths` | TEXT | NOT NULL | Fortalezas identificadas. |
| `improvement_areas` | TEXT | NOT NULL | Áreas de mejora sugeridas. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp de creación. |

**Relación:** Una sesión tiene muchas `phrase_muletillas` (1:N).

### Tabla: `phrase_muletillas`

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único. |
| `session_id` | UUID | FK → muletillas_sessions (CASCADE) | Sesión a la que pertenece. |
| `word` | VARCHAR(100) | NOT NULL | Palabra de relleno detectada (ej: "o sea", "eh"). |
| `count` | INTEGER | NOT NULL | Número de veces que aparece en la respuesta. |
| `severity` | VARCHAR(10) | NOT NULL | Severidad: "alta" (≥3 ocurrencias), "media" (2), "baja" (1). |
| `suggestion` | TEXT | NOT NULL | Sugerencia personalizada para evitar esta muletilla. |

### Migración

Archivo: `backend/alembic/versions/e7f3a1b2c9d0_add_muletillas_tables.py`

## 4. Esquemas de solicitud y respuesta

### `MuletillaDetectedSchema`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `word` | str | Palabra de relleno detectada. |
| `count` | int | Número de ocurrencias. |
| `severity` | str | "alta", "media" o "baja". |
| `suggestion` | str | Consejo para evitarla. |

### `MuletillasEvaluationResponse`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `overall_score` | float | Puntuación general (0-100). |
| `fluency_score` | float | Puntuación de fluidez (0-100). |
| `muletillas_score` | float | Puntuación de ausencia de muletillas (0-100). |
| `total_muletillas_count` | int | Total de muletillas detectadas. |
| `muletillas_per_minute` | float | Frecuencia de muletillas por minuto. |
| `muletillas_detected` | list[MuletillaDetectedSchema] | Lista de muletillas con detalle. |
| `feedback` | str | Retroalimentación general. |
| `strengths` | str | Fortalezas identificadas. |
| `improvement_areas` | str | Áreas de mejora. |

### `MuletillasSessionRequest`

Todos los campos de `MuletillasEvaluationResponse` más `question_text`.

### `MuletillasSessionResponse`

Igual al request más `id` y `created_at`.

### `MuletillasSessionListItem`

Respuesta compacta: `id`, `question_text`, `overall_score`, `total_muletillas_count`, `created_at`.

### `RandomQuestionResponse`

Un único campo: `question` (str) con la pregunta aleatoria.

## 5. Casos de uso

### `get_random_question()`

Retorna `random.choice(EVALUATION_QUESTIONS)`. Las 8 preguntas predefinidas son:

1. "Cuéntame sobre tu día de hoy."
2. "Describe tu lugar de trabajo o estudio."
3. "Explica en qué consiste tu pasatiempo favorito."
4. "Habla sobre una película o libro que hayas disfrutado recientemente."
5. "Describe un momento importante en tu vida."
6. "¿Qué te motiva a mejorar tu comunicación oral?"
7. "Habla sobre alguien que admiras y por qué."
8. "Describe el lugar donde creciste."

### `evaluate_response(audio_bytes, mime_type, question_text)`

**Flujo:**
1. Detecta si el audio contiene solo silencio.
2. Si es silencioso, retorna `_SILENCE_RESPONSE` (todos los scores en 0, lista de muletillas vacía).
3. Si hay contenido, invoca `GeminiMuletillasService.evaluate_response()`.

**Errores:** Excepciones de validación si el audio está vacío o es inválido.

### `save_muletillas_session(data, user, session)`

Crea `MuletillasSession` y, en la misma transacción, una `PhraseMuletillas` por cada muletilla en `data.muletillas_detected`. Hace commit al finalizar.

### `list_muletillas_sessions(user, session)`

Consulta todas las sesiones del usuario ordenadas por `created_at` descendente.

### `get_muletillas_session(session_id, user, session)`

Carga la sesión con `selectinload(muletillas_detected)`. Verifica que la sesión pertenezca al usuario.

**Errores:** `NotFoundError` si la sesión no existe. `ForbiddenError` si el usuario no es propietario.

## 6. Integración con Gemini AI

### `GeminiMuletillasService`

**Ubicación:** `backend/app/infrastructure/ai/muletillas_gemini.py`

**Modelo:** `gemini-2.5-flash`

**Entrada:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `audio_bytes` | bytes | Contenido del archivo de audio. |
| `mime_type` | str | Tipo MIME del audio. |
| `question_text` | str | Contexto de la pregunta para interpretar la respuesta. |

**Prompt:** Actúa como experto en comunicación oral. Detecta muletillas: "o sea", "este", "eh", "um", "ah", "básicamente", "tipo", "digamos", repeticiones sin sentido semántico y patrones de relleno recurrentes. Estima la duración del audio para calcular `muletillas_per_minute`. Califica la severidad: alta (3+ ocurrencias), media (2), baja (1).

**Salida JSON:**

```json
{
  "overall_score": 78,
  "fluency_score": 82,
  "muletillas_score": 72,
  "total_muletillas_count": 5,
  "muletillas_per_minute": 2.5,
  "muletillas_detected": [
    {
      "word": "este",
      "count": 3,
      "severity": "alta",
      "suggestion": "Sustituye 'este' por una pausa natural o una respiracion breve."
    }
  ],
  "feedback": "Retroalimentacion constructiva.",
  "strengths": "Fortalezas identificadas.",
  "improvement_areas": "Areas de mejora."
}
```

**Errores:** `GeminiMuletillasError` cuando la respuesta de Gemini no puede parsearse. Se registra el error con contexto suficiente para diagnóstico.

## 7. Endpoints de la API

### GET `/muletillas/questions/random`

Obtiene una pregunta aleatoria para iniciar una evaluación.

- **Autenticación:** Bearer token requerido
- **Respuesta (200 OK):** `RandomQuestionResponse`

---

### POST `/muletillas/evaluate`

Evalúa una respuesta de audio detectando muletillas.

- **Content-Type:** multipart/form-data
- **Autenticación:** Bearer token requerido

**Parámetros:**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `audio` | file | Sí | Archivo de audio (MP3, WAV, WebM, OGG). |
| `question_text` | string | Sí | Pregunta presentada al usuario. |

**Respuesta (200 OK):** `MuletillasEvaluationResponse`

**Errores:** `400` — audio vacío o parámetros faltantes. `422` — Gemini no pudo procesar el audio.

---

### POST `/muletillas/sessions`

Crea una nueva sesión persistiendo los resultados.

- **Código:** 201 Created
- **Body:** `MuletillasSessionRequest`
- **Respuesta:** `MuletillasSessionResponse`

---

### GET `/muletillas/sessions`

Lista todas las sesiones del usuario en orden descendente.

- **Respuesta (200 OK):** `list[MuletillasSessionListItem]`

---

### GET `/muletillas/sessions/{session_id}`

Detalles completos de una sesión con todas las muletillas detectadas.

- **Respuesta (200 OK):** `MuletillasSessionResponse`
- **Errores:** `404` — sesión no existe. `403` — sesión pertenece a otro usuario.
