# Muletillas — Documentación Backend

## 1. Descripción funcional

El módulo de Muletillas ayuda al usuario a identificar y reducir palabras de relleno ("o sea", "este", "eh", etc.). Flujo:

1. El frontend pide una pregunta abierta al endpoint random.
2. El usuario graba su respuesta.
3. El frontend manda el audio al endpoint de evaluación. Gemini AI devuelve scores y la lista de muletillas detectadas con su severidad y frecuencia.
4. El frontend agrega los resultados (incluida la lista de muletillas) y los manda al endpoint de creación de sesión.
5. El backend persiste solo las métricas agregadas y el conteo por palabra normalizada; el feedback verbal de Gemini se descarta tras mostrarlo en la UI.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/muletillas.py` | Endpoints HTTP (random + evaluate + sessions CRUD), mapeo de errores. |
| Schemas | `backend/app/presentation/schemas/muletillas.py` | Contratos Pydantic v2 (per-respuesta efímero + sesión persistida). |
| Use cases | `backend/app/use_cases/muletillas/evaluate_response.py`, `sessions.py` | Llamada a Gemini con corte por silencio + persistencia con normalización de palabras. |
| Infra AI | `backend/app/infrastructure/ai/muletillas_gemini.py` | Cliente Gemini con prompt, schema (severity en inglés, scores integer) y catálogo de muletillas frecuentes. |
| Infra audio | `backend/app/infrastructure/audio/silence_detector.py` | Detector de silencio compartido. |
| Entidades | `backend/app/domain/entities/session.py`, `muletillas_metrics.py`, `muletillas_word_usage.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

Una sesión de muletillas se representa con tres tipos de filas: `sessions` raíz, `muletillas_metrics` 1:1 y N filas en `muletillas_word_usage`.

### `sessions` (raíz, compartida)

Para muletillas standalone: `module='muletillas'`, `parent_id=NULL`, `status='completed'`. `score` lo deriva el backend = `fluency_score`.

### `muletillas_metrics` (1:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `fluency_score` | SMALLINT | NOT NULL, CHECK 0-100 | Puntuación de fluidez agregada (única métrica overall del nuevo schema). |
| `muletillas_count` | INT | NOT NULL DEFAULT 0 | Total de muletillas (suma de `count` en `muletillas_word_usage`). |

### `muletillas_word_usage` (N:1 con `sessions`)

Una fila por palabra normalizada por sesión. PK compuesta evita duplicados. Permite consultas longitudinales tipo "top muletillas del usuario X en últimos N días".

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK compuesta + FK `sessions.id` ON DELETE CASCADE | Sesión a la que pertenece. |
| `word` | VARCHAR(100) | PK compuesta | Palabra normalizada (lowercase, trimmed, sin acentos). |
| `count` | INT | NOT NULL DEFAULT 1 | Veces que apareció en la sesión. |
| `severity` | muletilla_severity_enum | NOT NULL | `low`, `medium` o `high`. |

Índice `ix_muletillas_word ON word` para top-N globales o por usuario via JOIN con `sessions`.

### Decisiones de diseño

- **`score` = `fluency_score`** (derivado en backend). Único métrica overall del nuevo schema; precedente loudness.
- **`muletillas_count` derivado en backend** = `sum(w.count for w in words)`. El cliente no envía el total, evita la posibilidad de que diverja de la lista de palabras.
- **Word normalization server-side**: `lowercase + trim + strip accents` (NFKD). El cliente puede mandar "EH", "Êh" o "  eh  " y todo cae en `eh`. Si el cliente manda dos entradas que normalizan a la misma palabra, el use_case lanza `DuplicateMuletillaWordError` → 422.
- **Severity en inglés (`low|medium|high`) end-to-end**: el ENUM nativo de Postgres usa estas etiquetas. La prompt y `response_schema` de Gemini se actualizaron para que devuelva directamente en inglés (no traducimos en boundary).
- **Schema Gemini con `"integer"`** para los 4 score fields (preemptive, lección de las review previas).
- **Drops per JSON propuesta**:
  - `question_text` y `feedback`/`strengths`/`improvement_areas`: texto LLM sin valor longitudinal.
  - `muletillas_per_minute`: derivable de `muletillas_count / duration_ms`.
  - `muletillas_score` (separado de `fluency_score`): el nuevo schema colapsó las dos métricas overall en una.
  - `overall_score` ephemeral: el `score` de la sesión es derivado en backend.
  - `suggestion` por palabra: texto LLM, no se persiste; el cliente la muestra en UI.
- **PK compuesta `(session_id, word)`** en `muletillas_word_usage`: una sola fila por palabra por sesión. Si el futuro pide trackear cada ocurrencia con timestamp, hay que cambiar a PK sintética + columna `occurred_at`.

## 4. Esquemas

### Evaluación efímera (Gemini)

`MuletillaDetectedEphemeral`: `word`, `count` (>=1), `severity` (`low|medium|high`), `suggestion` (texto Gemini, no persistido).

`MuletillasEvaluationResponse`: `overall_score`, `fluency_score`, `muletillas_score` (todos 0-100, ephemerals), `total_muletillas_count`, `muletillas_per_minute` (float), `muletillas_detected`, `feedback`, `strengths`, `improvement_areas`.

`RandomQuestionResponse`: `question`.

### Persistido

`MuletillaWordInput`: `word` (1-100 chars, normaliza server-side), `count` (>=1), `severity` (`low|medium|high`).

`MuletillasMetricsInput`: `fluency_score` (0-100), `words` (lista, puede ir vacía si no se detectaron muletillas).

`MuletillasMetricsOutput`: `fluency_score`, `muletillas_count`.

`MuletillasSessionCreate`: `started_at`, `ended_at`, `metrics`. Validador: `ended_at > started_at`.

`MuletillasSessionDetail`: `id`, `user_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`, `metrics`, `words` (lista ordenada alfabéticamente).

`MuletillasSessionListItem`: `id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `muletillas_count`, `fluency_score`. Incluye los dos números más informativos para una card de timeline.

## 5. Casos de uso

### `evaluate_response(audio_bytes, mime_type, question_text)` — `evaluate_response.py`

1. Si el detector de silencio marca el audio como vacío → retorna `_SILENCE_RESPONSE` (todos scores 0, sin muletillas).
2. Si el detector falla → loggea warning y procede a Gemini.
3. Llama a `GeminiMuletillasService.evaluate_response` y retorna el dict.

### `get_random_question()` — `evaluate_response.py`

Retorna pregunta aleatoria del catálogo hardcoded `EVALUATION_QUESTIONS`. Pendiente: migrar al catálogo unificado `prompts` filtrado por `module='muletillas'`.

### `_normalize_word(word)` — `sessions.py`

Lowercase + trim + NFKD decompose + descartar combining marks. Resultado: forma canónica de la palabra para PK uniforme.

### `create_muletillas_session(db, user, payload)` — `sessions.py`

1. Normaliza cada palabra y verifica que no haya duplicados después de normalizar (sino `DuplicateMuletillaWordError` → 422).
2. Calcula `duration_ms` y `muletillas_count = sum(counts)`.
3. En una transacción inserta `sessions(module='muletillas', status='completed', parent_id=NULL)` + `muletillas_metrics` + N filas en `muletillas_word_usage`.

### `list_muletillas_sessions(db, user)`

JOIN `sessions + muletillas_metrics`, filtra `module='muletillas' AND parent_id IS NULL`, ordena por `started_at DESC`.

### `get_muletillas_session(db, user, session_id)`

Detalle con palabras ordenadas alfabéticamente. Retorna `None` para no-encontrado o cross-user.

## 6. Endpoints

- `GET /muletillas/questions/random` → 200, `{question}`. Hardcoded por ahora.
- `POST /muletillas/evaluate` — multipart con `audio`, `question_text` (Form). Retorna `MuletillasEvaluationResponse`. 502 si Gemini falla.
- `POST /muletillas/sessions` → 201 / 422 (incluye 422 por palabra duplicada tras normalización).
- `GET /muletillas/sessions` → 200, lista standalone ordenada por `started_at DESC`.
- `GET /muletillas/sessions/{id}` → 200 / 404.

Todos los endpoints requieren Bearer JWT.

## 7. Pendientes en el roadmap

- **Composición en sesión live**: cuando se reescriba `live`, `create_muletillas_session` debe aceptar `parent_id` opcional.
- **Sesiones abortadas**: hoy solo `status='completed'`.
- **Migrar `EVALUATION_QUESTIONS` al catálogo `prompts`**: agregar seed + endpoint genérico de prompts. Hoy está hardcoded en `evaluate_response.py`.
- **Cache efímera de feedback Gemini**: igual que pronunciación/acentuación, hoy el feedback solo vive en la respuesta inmediata del `/evaluate`.
- **MIME allowlist unificada para evaluate endpoints**: refactor pendiente entre los 3 módulos con Gemini.
