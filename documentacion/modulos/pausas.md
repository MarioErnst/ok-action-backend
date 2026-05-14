# Pausas — Documentación Backend

## 1. Descripción funcional

El módulo de Pausas registra sesiones donde el usuario practica el uso de silencios durante una respuesta hablada. El objetivo no es eliminar las pausas: es diferenciar entre pausas intencionales que ordenan el discurso, demasiadas pausas que cortan la fluidez, y pocas pausas que vuelven el habla apresurada.

El análisis de audio se hace en el frontend con Web Audio API. El backend recibe la sesión completa con métricas agregadas y dos responsabilidades:

1. Persistir la sesión bajo el esquema unificado.
2. Exponer el histórico standalone del usuario.

No realiza análisis de audio ni cálculos derivados.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/pauses.py` | Endpoints HTTP, mapeo de errores, traducción a esquemas. |
| Schemas | `backend/app/presentation/schemas/pauses.py` | Contratos Pydantic v2 con validación cruzada de invariantes. |
| Use cases | `backend/app/use_cases/pauses/sessions.py` | Persistencia y consultas; orquesta la transacción multi-tabla. |
| Entidades | `backend/app/domain/entities/session.py`, `pause_metrics.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

Una sesión de pausas se representa con dos filas: la raíz `sessions` y su 1:1 `pause_metrics`.

### `sessions` (raíz, compartida)

Para pausas standalone: `module='pauses'`, `parent_id=NULL`, `status='completed'`. Cuando se reescriba el módulo `live`, las nested usarán `parent_id=<live_id>`.

Columnas relevantes: `id`, `user_id`, `module`, `parent_id`, `started_at`, `ended_at`, `duration_ms` (derivado), `score` (recibido del cliente), `status`, `created_at`.

### `pause_metrics` (1:1 con `sessions`)

Métricas agregadas de la sesión.

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `pauses_count` | INT | NOT NULL DEFAULT 0 | Cantidad total de pausas detectadas. |
| `total_pause_ms` | INT | NOT NULL DEFAULT 0 | Suma de duración de todas las pausas. |
| `longest_pause_ms` | INT | NOT NULL DEFAULT 0 | Duración de la pausa más larga. |
| `silence_pct` | SMALLINT | NOT NULL, CHECK 0-100 | Porcentaje de silencio sobre el total de la sesión. |
| `prompt_id` | UUID | NULL FK `prompts.id` ON DELETE RESTRICT | Identifica qué prompt del catálogo practicó el usuario. NULL en filas previas a la migración del catálogo. |

### Decisiones de diseño

- **`pauses` (JSONB) eliminado**: el array completo de intervalos `(start_ms, end_ms, duration_ms)` se descartó intencionalmente. Servía para un eventual replay UI que nunca se construyó; ocupaba espacio y no aportaba valor analítico longitudinal.
- **`average_pause_ms` eliminado**: se deriva trivialmente de `total_pause_ms / pauses_count` en frontend cuando se necesita mostrar.
- **`classification` eliminado**: era una etiqueta string ("muchas", "pocas", "balanceadas") derivable de las métricas. La clasificación se hace en frontend con la fórmula que el negocio defina; el backend almacena hechos, no juicios.
- **Tipos de pausa (frontend)**: a partir del rollout de `voiceSegmentation`, el frontend clasifica cada silencio en `natural` (200-800ms, respiración/transición), `rhetorical` (800-2000ms, pausa intencional) o `break` (>2000ms o pausa dentro de palabra, problema). El backend no persiste el tipo — el conteo y suma agregada captan lo necesario para análisis longitudinal; el desglose ephemeral viaja en la respuesta HTTP para el feedback inmediato.
- **`prompt_id` referencia al catálogo `prompts`** (FK RESTRICT, NULLABLE): reemplaza el viejo `prompt_text` snapshot. El catálogo se seedea en `_seed_pause_prompts` (8 prompts iniciales) y el endpoint `GET /pauses/prompts/random` lo expone. RESTRICT impide borrar un prompt referenciado por sesiones; si quieres "deprecar" un prompt sin perder histórico, marca `is_active=false`. Filas previas a la migración mantienen `prompt_id=NULL` y siguen siendo válidas.
- **`silence_ratio` (FLOAT 0-1) → `silence_pct` (SMALLINT 0-100)**: alineado con la convención del schema (sufijo `_pct`, SMALLINT con CHECK).
- **Score viene del cliente**: la fórmula que combina `pauses_count`, `total_pause_ms`, `longest_pause_ms` y `silence_pct` para dar un 0-100 es subjetiva (depende de qué se considera "buen ritmo"). Sigue el precedente de phonation (no de loudness, donde el score sí es derivable trivialmente).
- **Validadores cruzados en schema**:
  - `pauses_count == 0 ⇒ total_pause_ms == 0 AND longest_pause_ms == 0` (sin pausas no puede haber duración).
  - `longest_pause_ms <= total_pause_ms` (la pausa más larga no puede superar al total).
  - `total_pause_ms <= duration_ms` (a nivel sesión: el silencio no puede ser mayor a la sesión completa).

## 4. Esquemas

### Entrada

`PauseMetricsInput`: `pauses_count` (>=0), `total_pause_ms` (>=0), `longest_pause_ms` (>=0), `silence_pct` (0-100), `prompt_id?` (UUID opcional, debe pertenecer a `module='pauses'` y estar `is_active`). Validador `validate_internal_consistency` aplica las reglas de cohesión.

`PausePromptOutput`: `id`, `text`. Devuelto por `GET /pauses/prompts/random`.

`PauseSessionCreate`: `started_at`, `ended_at`, `score` (0-100), `metrics`. Validador `validate_session_consistency` chequea `ended_at > started_at` y `total_pause_ms <= duration_ms`.

### Salida

`PauseSessionDetail`: `id`, `user_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`, `metrics`.

`PauseSessionListItem` (compacto): `id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `pauses_count`, `silence_pct`. Incluye los dos números más informativos para una card de timeline.

## 5. Casos de uso

### `create_pause_session(db, user, payload)`

En una transacción inserta `sessions(module='pauses', status='completed', parent_id=NULL)` con `duration_ms` derivado y `score` recibido + `pause_metrics` 1:1. Si el payload incluye `prompt_id`, valida que sea un prompt activo del módulo `pauses` antes de persistir; si no, lanza `PausePromptNotAvailableError` y el router devuelve 422 (previene que el cliente vincule la sesión a un prompt de otro módulo).

### `get_random_prompt(db)` / `get_prompt_by_id(db, prompt_id)` — `prompts.py`

Acceso al catálogo. `get_random_prompt` devuelve un prompt activo random (`ORDER BY random() LIMIT 1`) y lanza `NoPausePromptsError` si el catálogo está vacío (router → 503). `get_prompt_by_id` valida que el id sea conocido, esté activo y pertenezca al módulo `pauses`; devuelve `None` en cualquier otro caso.

### `list_pause_sessions(db, user)`

JOIN `sessions + pause_metrics`, filtro `module='pauses' AND parent_id IS NULL`, ordenado por `started_at DESC`. El filtro por `parent_id` excluye sesiones que sean parte de un live.

### `get_pause_session(db, user, session_id)`

Detalle. Retorna `None` para no-encontrado o cross-user (router → 404 sin distinguir, no se filtra existencia).

## 6. Endpoints

- `GET /pauses/prompts/random` → 200 `{id, text}` / 503 si el catálogo está vacío.
- `POST /pauses/sessions` → 201 / 422 (incluye 422 si `prompt_id` no es un prompt activo de pauses).
- `GET /pauses/sessions` → 200, lista standalone ordenada por `started_at DESC`.
- `GET /pauses/sessions/{id}` → 200 / 404.

Todos requieren Bearer JWT.

## 7. Pendientes en el roadmap

- **Composición en sesión live**: cuando se reescriba `live`, `create_pause_session` debe aceptar un `parent_id` opcional.
- **Sesiones abortadas**: hoy solo se persiste `status='completed'`.
- **Migración al catálogo `prompts`**: completada. `pause_metrics.prompt_id` (NULLABLE, FK RESTRICT) registra qué practicó el usuario en cada sesión. Las filas previas a la migración 0006 mantienen `prompt_id=NULL` y siguen siendo válidas. Pendiente: exponer `prompt_id` o el texto del prompt en `PauseSessionListItem` si se quiere mostrar la consigna en la card del timeline (hoy solo aparece en el detalle).
