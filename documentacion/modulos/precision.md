# Precisión — Documentación Backend

## 1. Descripción general

El módulo de Precisión evalúa la capacidad del usuario para responder preguntas de forma directa, relevante y concisa en voz alta. Está orientado a la comunicación oral efectiva en contextos profesionales y cotidianos.

El flujo funcional es el siguiente:

1. El usuario inicia una sesión de precisión. El sistema selecciona aleatoriamente una pregunta del banco fijo, evitando repetir preguntas recientes.
2. El usuario graba su respuesta en audio.
3. El backend envía el audio a Gemini AI, que evalúa tres dimensiones: `directness` (qué tan directa es la respuesta), `relevance` (qué tan pertinente es al tema preguntado) y `conciseness` (qué tan concisa y sin relleno innecesario).
4. Si el audio es ininteligible, los scores quedan en `null` y se marca `audio_intelligible = false`.
5. El sistema calcula un `overall_score` ponderado a partir de las tres dimensiones.
6. Al finalizar la sesión, se persisten todos los resultados. El usuario puede consultar el historial de sesiones anteriores.

## 2. Entidades de dominio

### PrecisionQuestion

Representa una pregunta del banco fijo. No se generan preguntas dinámicamente.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la pregunta. |
| `text` | TEXT | NOT NULL | Enunciado de la pregunta. |
| `category` | VARCHAR(100) | nullable | Categoría temática de la pregunta (ej. "laboral", "personal"). |
| `created_at` | TIMESTAMPTZ | NOT NULL | Fecha de inserción del registro. |

**Tabla:** `precision_questions`

### PrecisionSession

Representa una sesión completa de evaluación de precisión iniciada por un usuario.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la sesión. |
| `user_id` | UUID | FK → users (CASCADE) | Usuario propietario de la sesión. |
| `status` | VARCHAR(20) | NOT NULL | Estado de la sesión: `in_progress`, `completed`, `abandoned`. |
| `overall_score` | NUMERIC(5,2) | nullable | Puntuación global calculada al finalizar (0-100). Null mientras está en curso. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Fecha y hora de creación. |
| `finalized_at` | TIMESTAMPTZ | nullable | Fecha y hora de cierre de la sesión. |

**Tabla:** `precision_sessions`

**Relación:** Una sesión tiene uno o más `PrecisionRound` (relación 1:N).

### PrecisionRound

Representa una ronda individual dentro de una sesión: una pregunta y su respuesta evaluada.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la ronda. |
| `session_id` | UUID | FK → precision_sessions (CASCADE) | Sesión a la que pertenece. |
| `question_id` | UUID | FK → precision_questions | Referencia a la pregunta del banco. |
| `question_text` | TEXT | NOT NULL | Snapshot del texto de la pregunta en el momento de la ronda. |
| `round_index` | INTEGER | NOT NULL | Índice ordinal de la ronda en la sesión (0-based). |
| `directness` | NUMERIC(5,2) | nullable | Puntuación de directness (0-100). Null si audio ininteligible. |
| `relevance` | NUMERIC(5,2) | nullable | Puntuación de relevance (0-100). Null si audio ininteligible. |
| `conciseness` | NUMERIC(5,2) | nullable | Puntuación de conciseness (0-100). Null si audio ininteligible. |
| `overall_score` | NUMERIC(5,2) | nullable | Puntuación ponderada de la ronda. Null si audio ininteligible. |
| `audio_intelligible` | BOOLEAN | NOT NULL, DEFAULT true | Indica si Gemini pudo interpretar el audio. |
| `strengths` | ARRAY(TEXT) | nullable | Lista de aspectos positivos detectados en la respuesta. |
| `improvement_areas` | ARRAY(TEXT) | nullable | Lista de áreas de mejora detectadas. |
| `feedback` | TEXT | nullable | Retroalimentación narrativa generada por Gemini. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Fecha y hora de evaluación. |

**Tabla:** `precision_rounds`

## 3. Casos de uso

### `start_precision_session(user, session)`

Inicia una nueva sesión de precisión para el usuario autenticado. Crea un registro `PrecisionSession` con `status = in_progress`. Selecciona aleatoriamente una pregunta del banco, excluyendo las preguntas usadas en las últimas sesiones del usuario para evitar repetición inmediata. Retorna la sesión creada junto con la primera pregunta.

### `evaluate_precision_response(session_id, audio_bytes, mime_type, round_index, user, session)`

Recibe el audio de una respuesta y lo envía a `GeminiPrecisionService` para evaluación. Crea un `PrecisionRound` con los scores obtenidos. Si Gemini determina que el audio es ininteligible, persiste la ronda con `audio_intelligible = false` y todos los scores en `null`. Retorna el resultado de la ronda evaluada.

### `finalize_precision_session(session_id, user, session)`

Cierra una sesión en curso. Calcula el `overall_score` de la sesión como promedio de los `overall_score` de las rondas completadas (ignorando rondas con audio ininteligible). Actualiza el `status` a `completed` y registra `finalized_at`. Retorna la sesión con el score final.

### `abandon_precision_session(session_id, user, session)`

Marca una sesión como `abandoned` sin calcular scores. Se usa cuando el usuario interrumpe el flujo antes de completar las rondas. Las rondas ya evaluadas quedan registradas pero no se computan en el score de sesión.

### `get_precision_session(session_id, user, session)`

Carga una sesión con todos sus `PrecisionRound` asociados usando `selectinload`. Valida que `user_id` coincida con el usuario autenticado antes de devolver el resultado. Retorna `403` si la sesión pertenece a otro usuario y `404` si no existe.

### `get_precision_history(user, session)`

Consulta las sesiones completadas del usuario, ordenadas por `created_at` descendente. Solo incluye sesiones con `status = completed`. Retorna una lista compacta con `id`, `overall_score` y `created_at`.

## 4. Endpoints

### POST `/precision/sessions`

Inicia una nueva sesión de precisión.

- **Método:** POST — **Código:** 201 Created
- **Autenticación:** Bearer token requerido
- **Body:** vacío (no requiere parámetros)
- **Respuesta:** objeto con `session_id`, `status`, `question` (id y texto de la primera pregunta), `created_at`

---

### POST `/precision/sessions/{session_id}/rounds`

Envía el audio de una respuesta para evaluación dentro de una sesión activa.

- **Método:** POST — **Código:** 200 OK
- **Content-Type:** multipart/form-data
- **Parámetros de ruta:** `session_id` (UUID)
- **Parámetros de formulario:** `audio` (archivo), `round_index` (integer)
- **Respuesta:** objeto `PrecisionRound` con scores, `audio_intelligible`, `strengths`, `improvement_areas`, `feedback`

---

### POST `/precision/sessions/{session_id}/finalize`

Finaliza una sesión activa y calcula el score consolidado.

- **Método:** POST — **Código:** 200 OK
- **Parámetros de ruta:** `session_id` (UUID)
- **Body:** vacío
- **Respuesta:** sesión completa con `overall_score`, `status = completed`, `finalized_at` y lista de rondas

---

### PATCH `/precision/sessions/{session_id}/abandon`

Abandona una sesión sin calcular resultados.

- **Método:** PATCH — **Código:** 200 OK
- **Parámetros de ruta:** `session_id` (UUID)
- **Body:** vacío
- **Respuesta:** sesión con `status = abandoned`

---

### GET `/precision/sessions/{session_id}`

Retorna los detalles completos de una sesión específica con todas sus rondas.

- **Método:** GET — **Código:** 200 OK
- **Parámetros de ruta:** `session_id` (UUID)
- **Respuesta:** sesión con lista completa de `PrecisionRound`
- **Errores:** `403` si la sesión no pertenece al usuario; `404` si no existe

---

### GET `/precision/history`

Lista las sesiones completadas del usuario autenticado.

- **Método:** GET — **Código:** 200 OK
- **Respuesta:** lista de objetos con `id`, `overall_score`, `created_at`, ordenada descendentemente por fecha

## 5. Servicio Gemini

### `GeminiPrecisionService`

**Ubicación:** `backend/app/infrastructure/ai/precision_gemini.py`

**Modelo:** `gemini-2.5-flash`

**Responsabilidad:** recibir el audio de la respuesta del usuario junto con el texto de la pregunta, y retornar un objeto JSON con las tres dimensiones de evaluación más metadatos de feedback.

**Parámetros de entrada:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `audio_bytes` | bytes | Contenido binario del archivo de audio. |
| `mime_type` | str | Tipo MIME del audio: webm, mp4, ogg, wav, mpeg. |
| `question_text` | str | Texto exacto de la pregunta que el usuario respondió. |

**Esquema de respuesta JSON:**

```json
{
  "audio_intelligible": true,
  "directness": 80,
  "relevance": 75,
  "conciseness": 70,
  "strengths": ["Respuesta clara desde el inicio", "Sin rodeos innecesarios"],
  "improvement_areas": ["Podría ser más concisa en la segunda parte"],
  "feedback": "La respuesta aborda el tema de forma directa. Se sugiere eliminar repeticiones en la segunda mitad para ganar concisión."
}
```

Si `audio_intelligible` es `false`, los campos `directness`, `relevance`, `conciseness`, `strengths` e `improvement_areas` se omiten o quedan en `null`. Solo se incluye `feedback` con una indicación de que el audio no pudo procesarse.

**Prompt template:** El prompt instruye a Gemini a actuar como evaluador de comunicación oral efectiva en español. Se le proporciona la pregunta original y se le pide que evalúe únicamente la pertinencia, dirección y economía del lenguaje de la respuesta, sin considerar acento, pronunciación ni ruido de fondo.

**Por qué no se penaliza el ruido de fondo:** el ruido ambiental es un factor externo al hablante que no refleja su capacidad comunicativa. Penalizarlo introduciría varianza injusta según el entorno del usuario (transporte, oficina abierta, hogar). El módulo mide competencia discursiva, no calidad de grabación.

## 6. Fórmula de scores

### Overall score por ronda

```
overall = round(relevance * 0.4 + directness * 0.3 + conciseness * 0.3)
```

**Por qué `relevance` tiene mayor peso (0.4):** una respuesta puede ser directa y concisa pero completamente fuera de tema, lo que la hace inútil comunicativamente. La pertinencia al tema es la condición más crítica de una respuesta efectiva. Directness y conciseness son igualmente importantes entre sí, pero ambas subordinadas a que la respuesta sea relevante.

### Overall score de sesión

Se calcula como el promedio simple de los `overall_score` de todas las rondas con `audio_intelligible = true`. Las rondas ininteligibles no se incluyen en el cálculo para no penalizar al usuario por problemas técnicos ajenos a su desempeño.

### Manejo de audio ininteligible

Cuando Gemini devuelve `audio_intelligible = false`:

- Los campos `directness`, `relevance`, `conciseness` y `overall_score` del `PrecisionRound` se persisten como `null`.
- `audio_intelligible` se registra como `false`.
- El `feedback` indica que el audio no pudo ser interpretado.
- La ronda queda registrada pero se excluye del cálculo del score de sesión.

## 7. Decisiones de diseño

### Banco de preguntas fijo en lugar de generación dinámica con IA

Las preguntas se almacenan en la tabla `precision_questions` y se seleccionan aleatoriamente en cada sesión. Se descartó la generación dinámica por Gemini por tres razones: (1) elimina latencia adicional al iniciar la sesión, (2) garantiza que todas las preguntas tengan una dificultad y estructura validadas manualmente, y (3) permite controlar el vocabulario y los temas para que sean apropiados al nivel del producto sin depender de la variabilidad del modelo generativo.

### ARRAY(TEXT) en PostgreSQL para `strengths` e `improvement_areas`

Se usa `ARRAY(Text)` de PostgreSQL en lugar de JSONB o una tabla separada porque la información es una lista plana de cadenas sin estructura anidada. ARRAY nativo es más simple de consultar (`ANY`, `unnest`) y más eficiente en almacenamiento que JSONB para listas de strings. Una tabla separada habría agregado complejidad de joins innecesaria para datos que siempre se consumen junto con la ronda.

### `question_text` como snapshot en PrecisionRound (no solo FK)

Aunque `question_id` referencia la pregunta original en `precision_questions`, se almacena también `question_text` como copia en el momento de la ronda. Esto garantiza que el historial del usuario refleje exactamente el texto que vio cuando respondió, incluso si la pregunta es editada o eliminada del banco en el futuro. La FK sirve para trazabilidad; el snapshot sirve para integridad histórica.

### Estrategia para no repetir preguntas recientes

Al iniciar una sesión, el caso de uso consulta los `question_id` usados en las últimas N sesiones del usuario (donde N es configurable) y los excluye de la selección aleatoria. Si el banco tiene pocas preguntas y todas han sido usadas recientemente, el sistema selecciona igualmente de forma aleatoria sin restricción para evitar bloquear al usuario. Esta lógica vive en el caso de uso, no en la base de datos, para mantener la flexibilidad de ajustar N sin migraciones.
