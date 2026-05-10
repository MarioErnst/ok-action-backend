# Versatilidad Lingüística — Documentación Backend

## 1. Descripción funcional

El módulo de Versatilidad Lingüística entrena al usuario a usar vocabulario variado y rico al hablar. Tiene dos modos:

- **guided**: el backend selecciona N preguntas del catálogo `prompts`. El usuario responde una por una; cada round es evaluado contra la pregunta.
- **free**: el usuario habla libremente sin pregunta asignada. Cada round es una grabación libre.

El lifecycle es stateful como precision: start → N×evaluate → finalize|abandon.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/linguistic_versatility.py` | Endpoints HTTP del lifecycle, orquestación Gemini, mapeo de errores. |
| Schemas | `backend/app/presentation/schemas/linguistic_versatility.py` | Contratos Pydantic v2 del request/response de cada paso. |
| Use cases | `backend/app/use_cases/linguistic_versatility/sessions.py` | Lógica de negocio del lifecycle. |
| Infra AI | `backend/app/infrastructure/ai/linguistic_versatility_gemini.py` | Cliente Gemini con dos prompts (guided/free). Schema devuelve INTEGER 0-100. |
| Seed | `backend/app/infrastructure/db/seed.py` | Inserta 10 prompts iniciales (idempotente). |
| Entidades | `backend/app/domain/entities/session.py`, `linguistic_versatility_metrics.py`, `linguistic_versatility_round.py`, `prompt.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

### `sessions` (raíz, compartida)

Para linguistic_versatility standalone: `module='linguistic_versatility'`, `parent_id=NULL`. `status` evoluciona `active` → (`completed`|`aborted`).

### `linguistic_versatility_metrics` (1:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `mode` | linguistic_versatility_mode_enum | NOT NULL DEFAULT `guided` | `guided` o `free`. |
| `rounds_total` | INT | NOT NULL | Cantidad planeada al hacer start. |
| `rounds_completed` | INT | NOT NULL DEFAULT 0 | Incrementa con cada `evaluate_round` exitoso. |
| `vocabulary_richness_avg` | SMALLINT NULL | CHECK 0-100 | Promedio agregado al finalize. NULL si no hubo rounds inteligibles. |

### `linguistic_versatility_rounds` (N:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK compuesta + FK `sessions.id` ON DELETE CASCADE | Sesión a la que pertenece. |
| `round_index` | SMALLINT | PK compuesta | Asignado por el cliente (0..N-1). |
| `prompt_id` | UUID NULL | FK `prompts.id` ON DELETE RESTRICT | Requerido en guided, NULL en free. |
| `score` | SMALLINT NULL | CHECK 0-100 | Versatility score del round. NULL si `is_audio_intelligible=false`. |
| `vocabulary_richness` | SMALLINT NULL | CHECK 0-100 | Riqueza léxica del round. NULL si inintelegible. |
| `is_audio_intelligible` | BOOLEAN | NOT NULL DEFAULT TRUE | Gemini decide. |

Índice `ix_lex_rounds_prompt ON prompt_id` para análisis longitudinal por pregunta.

### Decisiones de diseño

- **Modo dual `guided` / `free`**: cubre dos UX distintos sin duplicar tablas. La diferencia se reduce a `prompt_id` NULLABLE + qué prompt template envía Gemini.
- **`vocabulary_richness` cambió de 1/2/3 (Gemini viejo) a 0-100**: el JSON propuesta usa SMALLINT 0-100 para todos los `_pct`/`_score`. Actualicé la prompt y el `response_schema` de Gemini para que devuelva 0-100 directamente, evitando un mapping arbitrario en boundary. La banda conceptual sigue clara (0-33 básico, 34-66 intermedio, 67-100 avanzado).
- **`score` por round = `versatility_score` de Gemini**: única métrica overall canónica. `score` por sesión al finalize = avg de rounds inteligibles.
- **`vocabulary_richness_avg`** en metrics: avg de rounds inteligibles, calculado al finalize.
- **`prompt_id` mode mismatch → 422**: en guided es obligatorio, en free debe omitirse. `PromptModeMismatchError` el use_case lanza, el router lo mapea.
- **Invariantes de evaluate_round (lección de precision review)**:
  - `round_index ∈ [0, rounds_total)` → `RoundIndexOutOfRangeError` → 422.
  - Duplicate composite PK → catch IntegrityError → `RoundAlreadyEvaluatedError` → 409 (rollback evita doble-incremento de `rounds_completed`).
- **Drops per JSON**: `transcript`, `feedback`, `strengths`, `improvement_areas`, `question_text`. Texto LLM o snapshot duplicado del catálogo.
- **`abandon` idempotente** sobre aborted; 409 sobre completed.
- **Validación dual de `prompt_id`** (sólo en guided): router fetch para obtener texto Gemini + use_case re-check como invariante.

## 4. Esquemas

### Start

`StartSessionRequest`: `mode` (`guided`|`free`) + `rounds_total` (1-20).

`StartSessionResponse`: `session_id`, `started_at`, `mode`, `rounds_total`, `prompts` (lista vacía en free).

### Evaluate per round

Multipart: `audio` (UploadFile), `round_index` (>=0), `prompt_id` (UUID opcional, requerido en guided).

`EvaluateRoundResponse`: `round_index`, `prompt_id?`, `is_audio_intelligible`, `score?` (0-100), `vocabulary_richness?` (0-100), `feedback` (Gemini, ephemeral).

### Finalize

`FinalizeSessionResponse`: `session_id`, `status` (`completed`), `score?`, `rounds_completed`, `rounds_total`, `vocabulary_richness_avg?`.

### Detail / List

`LinguisticVersatilityRoundOutput`: round_index, prompt_id?, score?, vocabulary_richness?, is_audio_intelligible.

`LinguisticVersatilityMetricsOutput`: mode, rounds_total, rounds_completed, vocabulary_richness_avg?.

`LinguisticVersatilitySessionDetail`: id, user_id, started_at, ended_at?, duration_ms?, score?, status, created_at, metrics, rounds.

`LinguisticVersatilitySessionListItem`: id + timeline meta + mode + counts + vocabulary_richness_avg?.

## 5. Casos de uso (`sessions.py`)

- `start_linguistic_versatility_session(db, user, mode, rounds_total)`: crea sesión + metrics; si guided, pickup N prompts del catálogo (sino `NotEnoughPromptsError` → 503). En free, prompts=[].
- `evaluate_round(db, user, session_id, round_index, prompt_id, gemini_evaluation)`: valida sesión activa + round_index bounds + prompt-mode pairing + prompt válido (si guided), persiste round con scores derivados, incrementa rounds_completed. Mapea PK violation a `RoundAlreadyEvaluatedError`.
- `finalize_linguistic_versatility_session(db, user, session_id)`: agrega scores, marca completed, computa duration_ms.
- `abandon_linguistic_versatility_session(db, user, session_id)`: marca aborted; idempotente sobre aborted, falla sobre completed.
- `list_linguistic_versatility_sessions(db, user)`: timeline con todas las status, filter `parent_id IS NULL`.
- `get_linguistic_versatility_session(db, user, session_id)`: detalle. None para no-encontrado o cross-user → 404.

### Helper privado

- `_load_active_session(db, user, session_id) -> (Session, Metrics)`: carga + valida ownership + status, lanza excepciones tipadas.

## 6. Endpoints

- `POST /linguistic-versatility/sessions` → 201 / 503.
- `POST /linguistic-versatility/sessions/{id}/rounds` — multipart audio + round_index + prompt_id?. → 200 / 404 / 409 (sesión no activa o round ya evaluado) / 422 (round bounds, mode mismatch, prompt inválido) / 502 (Gemini).
- `POST /linguistic-versatility/sessions/{id}/finalize` → 200 / 404 / 409.
- `PATCH /linguistic-versatility/sessions/{id}/abandon` → 204 / 404 / 409.
- `GET /linguistic-versatility/sessions` → 200 lista todas las status.
- `GET /linguistic-versatility/sessions/{id}` → 200 / 404.

URL kebab (`/linguistic-versatility`) por convención web; el module enum interno sigue snake.

Todos los endpoints requieren Bearer JWT.

## 7. Pendientes en el roadmap

- **Composición en sesión live**: `start_linguistic_versatility_session` debe aceptar `parent_id` opcional cuando lo invoque el orquestador del módulo `live`.
- **Anti-repetición de prompts** (guided): el viejo código no excluía recientes; podría agregarse un join contra rounds del usuario en sesiones recientes. Defer mientras el catálogo sea pequeño.
- **MIME allowlist unificada**: igual que precision/pronunciation/accentuation/muletillas.
- **Cache efímera de feedback Gemini**: hoy solo vive en la respuesta inmediata.
