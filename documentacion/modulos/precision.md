# Precisión — Documentación Backend

## 1. Descripción funcional

El módulo de Precisión entrena al usuario a responder preguntas abiertas de forma **relevante**, **directa** y **concisa**. El flujo, a diferencia de otros módulos, es stateful con varios endpoints en secuencia:

1. **Start**: el frontend pide una sesión con N rounds. El backend crea la sesión activa y selecciona N prompts del catálogo `prompts` filtrado por `module='precision'` y `is_active=true`.
2. **Evaluate per round**: para cada round el frontend manda el audio + `round_index` + `prompt_id`. El backend llama a Gemini con el texto del prompt, persiste los scores y retorna el resultado con feedback ephemeral.
3. **Finalize**: el frontend cierra la sesión. El backend agrega scores por dimensión, calcula `score` global como promedio de rounds inteligibles, y marca `status='completed'` con `ended_at` y `duration_ms`.
4. **Abandon**: alternativa al finalize si el usuario interrumpe. Marca `status='aborted'` con `ended_at`.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/precision.py` | Endpoints HTTP del lifecycle, llamada a Gemini, mapeo de errores. |
| Schemas | `backend/app/presentation/schemas/precision.py` | Contratos Pydantic v2 del request/response de cada paso. |
| Use cases | `backend/app/use_cases/precision/sessions.py` | Lógica de negocio del lifecycle (start/evaluate/finalize/abandon/list/get). |
| Infra AI | `backend/app/infrastructure/ai/precision_gemini.py` | Cliente Gemini (3-dim scoring + transcript + feedback). Schema ya devuelve INTEGER. |
| Seed | `backend/app/infrastructure/db/seed.py` | Inserta 10 prompts de precision iniciales (idempotente). |
| Entidades | `backend/app/domain/entities/session.py`, `precision_metrics.py`, `precision_round.py`, `prompt.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

Una sesión de precisión se representa con tres tipos de filas: `sessions` raíz, `precision_metrics` 1:1 y N filas en `precision_rounds`.

### `sessions` (raíz, compartida)

Para precision standalone: `module='precision'`, `parent_id=NULL`. El `status` evoluciona `active` → (`completed`|`aborted`). Mientras `active`: `ended_at`, `duration_ms`, `score` son NULL.

### `precision_metrics` (1:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `mode` | precision_mode_enum | NOT NULL DEFAULT `standalone` | `standalone` o `live` (cuando se rehaga el módulo `live`, las nested usarán este valor). |
| `rounds_total` | INT | NOT NULL | Cantidad planeada al hacer start. |
| `rounds_completed` | INT | NOT NULL DEFAULT 0 | Incrementa con cada `evaluate_round` exitoso. |
| `relevance_score` | SMALLINT NULL | CHECK 0-100 | Promedio de rounds inteligibles. NULL hasta finalize. |
| `directness_score` | SMALLINT NULL | CHECK 0-100 | Promedio de rounds inteligibles. NULL hasta finalize. |
| `conciseness_score` | SMALLINT NULL | CHECK 0-100 | Promedio de rounds inteligibles. NULL hasta finalize. |

### `precision_rounds` (N:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK compuesta + FK `sessions.id` ON DELETE CASCADE | Sesión a la que pertenece. |
| `round_index` | SMALLINT | PK compuesta | Asignado por el cliente (0..N-1). |
| `prompt_id` | UUID | NOT NULL FK `prompts.id` ON DELETE RESTRICT | El prompt usado en este round. RESTRICT impide borrar prompts referenciados. |
| `score` | SMALLINT NULL | CHECK 0-100 | Overall del round. NULL si `is_audio_intelligible=false`. |
| `relevance_score` | SMALLINT NULL | CHECK 0-100 | NULL si audio inintelegible. |
| `directness_score` | SMALLINT NULL | CHECK 0-100 | NULL si audio inintelegible. |
| `conciseness_score` | SMALLINT NULL | CHECK 0-100 | NULL si audio inintelegible. |
| `is_audio_intelligible` | BOOLEAN | NOT NULL DEFAULT TRUE | Gemini decide; si false, scores son NULL. |

Índice `ix_precision_rounds_prompt ON prompt_id` para análisis longitudinal por pregunta.

### Decisiones de diseño

- **Lifecycle stateful**: precision no usa el patrón "submit completed session" porque el UX requiere mostrar score por round antes de avanzar al siguiente. Cada round implica una llamada Gemini sirviendo un audio del usuario.
- **Catálogo `prompts`**: el viejo `precision_questions` se eliminó. Las preguntas ahora viven en `prompts` (`module='precision'`). 10 prompts iniciales se insertan vía `seed.py`.
- **`prompt_id` con FK RESTRICT**: borrar un prompt referenciado por sesiones lo bloquea. Si quieres "deprecar" un prompt sin perder histórico, marca `is_active=false` (no aparecerá en futuras sesiones, pero los rounds antiguos siguen siendo válidos).
- **`round_index` por cliente**: el frontend asigna round_index 0..N-1 según orden de prompts. Backend solo valida que la combinación `(session_id, round_index)` no duplique (composite PK lo enforza). No tracea qué prompt fue asignado a qué round; confía en que el cliente honre la asignación inicial. Riesgo bajo (usuario solo puede "elegir prompts más fáciles" para sí mismo, no impacta a terceros).
- **Score per round derivado server-side**: `round(0.4*relevance + 0.3*directness + 0.3*conciseness)`. Pesos heredados del código viejo para no romper la percepción del usuario. Cambio centralizado en `_round_score`.
- **Score per session derivado en finalize** = avg de rounds inteligibles. Sub-scores agregados (relevance/directness/conciseness en metrics) también promedios.
- **Scores NULL si audio inintelegible**: el round queda persistido (incrementa `rounds_completed`) pero sin scores. Si TODOS los rounds resultan inintelegibles, finalize deja `score=NULL` en sessions y los 3 sub-scores agregados también NULL.
- **Validación dual de `prompt_id`**: el router lo verifica primero (necesita el texto para Gemini, falla con 422 sin pegarle a Gemini si no existe). El use_case lo re-verifica como invariante de su propia responsabilidad. 2 queries baratas, separación limpia router-vs-use_case.
- **Drops per JSON**: `transcript`, `noise_level`, `feedback`, `strengths`, `improvement_areas`, `question_text`, `audio_duration_secs`. Texto LLM, datos sin valor longitudinal, snapshot duplicado de catálogo.
- **`abandon` idempotente**: llamar abandon sobre una sesión ya `aborted` es un no-op (frontend puede tocar el botón dos veces sin error). Llamar sobre `completed` falla con 409 (no se puede revertir).

## 4. Esquemas

### Start

`StartSessionRequest`: `rounds_total` (1-20).

`StartSessionResponse`: `session_id`, `started_at`, `rounds_total`, `prompts` (lista de `PromptOut` con id+text+category+difficulty).

### Evaluate per round

Multipart Form (no es Pydantic, ver `EvaluateRoundRequestForm` como mirror documentación-only): `audio` (UploadFile), `round_index` (>=0), `prompt_id` (UUID).

`EvaluateRoundResponse`: `round_index`, `prompt_id`, `is_audio_intelligible`, `score?`, 3 `*_score?`, `transcript`, `feedback`, `strengths` (list), `improvement_areas` (list).

### Finalize

`FinalizeSessionResponse`: `session_id`, `status` ("completed"), `score?`, `rounds_completed`, `rounds_total`, 3 `*_score?` agregados.

### Detail / List

`PrecisionRoundOutput`: round_index, prompt_id, score?, 3 sub-scores?, is_audio_intelligible.

`PrecisionMetricsOutput`: mode, rounds_total, rounds_completed, 3 *_score?.

`PrecisionSessionDetail`: id, user_id, started_at, ended_at?, duration_ms?, score?, status, created_at, metrics, rounds.

`PrecisionSessionListItem`: id, started_at, ended_at?, duration_ms?, score?, status, rounds_total, rounds_completed.

## 5. Casos de uso (`sessions.py`)

- `start_precision_session(db, user, rounds_total)`: crea sesión activa + metrics; selecciona N prompts random del catálogo. Si la cantidad disponible < rounds_total, lanza `NotEnoughPromptsError` → router 503.
- `evaluate_round(db, user, session_id, round_index, prompt_id, gemini_evaluation)`: valida sesión activa + prompt válido, persiste round con scores derivados. Lanza `SessionNotFoundError`/`SessionNotActiveError`/`PromptNotAvailableError` → router 404/409/422.
- `finalize_precision_session(db, user, session_id)`: agrega scores, marca completed, computa duration_ms.
- `abandon_precision_session(db, user, session_id)`: marca aborted; idempotente sobre aborted, falla sobre completed.
- `list_precision_sessions(db, user)`: timeline incluyendo todas las status (active/completed/aborted), filtrando `parent_id IS NULL`.
- `get_precision_session(db, user, session_id)`: detalle. None para no-encontrado o cross-user → router 404.

### Helpers privados

- `_round_score(rel, dir, con) -> int`: fórmula `round(0.4*rel + 0.3*dir + 0.3*con)`.
- `_load_active_session(db, user, session_id) -> (Session, PrecisionMetrics)`: carga + valida ownership + status, lanza excepciones tipadas.

## 6. Endpoints

- `POST /precision/sessions` → 201 `StartSessionResponse` / 503 (catálogo insuficiente).
- `POST /precision/sessions/{session_id}/rounds` — multipart audio + round_index + prompt_id. → 200 `EvaluateRoundResponse` / 404 (sesión) / 409 (no activa) / 422 (prompt inválido) / 502 (Gemini).
- `POST /precision/sessions/{session_id}/finalize` → 200 `FinalizeSessionResponse` / 404 / 409.
- `PATCH /precision/sessions/{session_id}/abandon` → 204 / 404 / 409.
- `GET /precision/sessions` → 200 lista con todos los status.
- `GET /precision/sessions/{id}` → 200 / 404.

Todos los endpoints requieren Bearer JWT.

## 7. Pendientes en el roadmap

- **Composición en sesión live**: `start_precision_session` debe aceptar `mode='live'` cuando lo invoque el orquestador del módulo `live`, y la sesión debe asociarse vía `parent_id`. Hoy hardcoded a `standalone`.
- **Anti-repetición de prompts**: el viejo código excluía los últimos N prompts vistos por el usuario. Reintroducir con un join sobre `precision_rounds` filtrado por sesiones recientes del usuario; deferred mientras el catálogo sea pequeño.
- **MIME allowlist unificada**: implementada en `app/infrastructure/audio/mime.py` (ver `documentacion/audio-mime-allowlist.md`). El endpoint de evaluación por ronda rechaza con 415 si el `Content-Type` no está en la allowlist.
- **Cache efímera de feedback Gemini**: `transcript`/`feedback`/`strengths`/`improvement_areas` solo viven en la respuesta inmediata.
