# Sesión Live (Composición) — Documentación Backend

## 1. Descripción funcional

Una sesión "live" agrupa varias sesiones de módulos individuales en una unidad de práctica. Bajo el esquema uniforme la composición se modela vía `parent_id`: cada sesión componente vive en su propia tabla (`<modulo>_metrics` + `sessions(module=<modulo>)`) y apunta a la sesión live como padre.

Flujo conceptual:

1. Frontend abre la sesión live: `POST /live/sessions` → recibe `session_id`.
2. Frontend ejecuta uno o varios módulos componentes (phonation, loudness, etc.) cada uno con su propio endpoint, pasando `parent_id=<live_id>` cuando esté wired (ver pendiente).
3. Frontend cierra: `POST /live/sessions/{id}/finalize` → backend agrega `score = avg(hijos completados)` y marca `status='completed'`, `live_metrics(stop_reason='completed')`.
4. Si el usuario interrumpe: `PATCH /live/sessions/{id}/abandon` con `stop_reason ∈ {user_stop, time_limit, error}` → marca `aborted` con el motivo.

A diferencia del viejo `live_session` (WebSocket que analizaba audio con Gemini para múltiples dimensiones simultáneamente), el nuevo `live` es **HTTP puro y solo orquesta composición**. No tiene streaming ni llamadas Gemini propias; cada módulo componente es responsable de su propia evaluación.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/live.py` | Endpoints HTTP del lifecycle (start, finalize, abandon, list, get). |
| Schemas | `backend/app/presentation/schemas/live.py` | Contratos Pydantic v2. |
| Use cases | `backend/app/use_cases/live/sessions.py` | Lógica del lifecycle, agregación de score sobre hijos. |
| Entidades | `backend/app/domain/entities/session.py`, `live_metrics.py` | Modelo SQLAlchemy. |

## 3. Modelo de datos

### `sessions` (raíz, compartida)

Para live: `module='live'`, `parent_id=NULL` (las live nunca son hijas de otra live en el schema actual). `status` evoluciona `active` → (`completed`|`aborted`).

`score` se asigna al finalize/abandon como avg de los hijos completados. NULL si no hay hijos completados con score.

### `live_metrics` (1:1 con `sessions`, creada al cierre)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `stop_reason` | stop_reason_enum | NOT NULL | `user_stop`, `time_limit`, `error` (al abandon) o `completed` (al finalize). |

### Composición vía `sessions.parent_id`

La lista de módulos contenidos por una live se obtiene con:

```sql
SELECT * FROM sessions WHERE parent_id = <live_id>;
```

No hay tabla intermedia ni "ordering" persistido — el orden se infiere del `started_at` de cada hijo.

### Decisiones de diseño

- **Live es composición, no orquestador de audio**: el viejo módulo era un WS que analizaba audio para múltiples dims en paralelo. El nuevo es HTTP puro y solo gestiona el contenedor padre. Cada módulo se ejecuta independientemente con su flujo propio.
- **`live_metrics` se crea al cierre, no al inicio**: `stop_reason` es NOT NULL y no tiene un valor sentinela honesto durante `active`. Diferir la inserción a finalize/abandon mantiene el modelo veraz; consultas durante `active` ven `metrics: null` y eso refleja el estado real.
- **`score = avg de hijos `completed` con score no nulo`**: implementado server-side via `SELECT AVG(score) FROM sessions WHERE parent_id=<live_id> AND status='completed' AND score IS NOT NULL`. Postgres ignora NULLs en AVG por defecto; explícitamente filtramos status='completed' para no inflar con sesiones aborted-but-with-score.
- **`stop_reason='completed'` reservado para finalize**: el endpoint abandon rechaza `completed` con un Literal. Si alguien skippea el schema (caller interno futuro) el use_case también lo rechaza con ValueError. Defense in depth.
- **No se borra una live si tiene hijos**: la FK CASCADE en hijos es a `sessions.id`. Borrar la live cascadea a los hijos automáticamente — quizás indeseable si el usuario solo quiere "abandonar la composición" pero conservar las sesiones individuales. No hay endpoint de borrado por ahora; cualquier delete debe pasar por una decisión consciente.
- **List endpoint trae `children_count`** vía subconsulta correlacionada — evita N+1 sin requerir eager loading.
- **WebSocket viejo fue eliminado completamente**: `app/use_cases/live_session/`, `app/presentation/{routers,schemas}/live_session.py` y `app/infrastructure/ai/live_gemini.py` ya no existen. Si en el futuro se quiere re-introducir streaming multi-dim, sería como módulo separado encima del modelo de composición.

## 4. Esquemas

### Entrada

`AbandonSessionRequest`: `stop_reason ∈ {"user_stop", "time_limit", "error"}` (excluye explícitamente `"completed"`).

### Salida

`StartSessionResponse`: `session_id`, `started_at`.

`FinalizeSessionResponse`: `session_id`, `status="completed"`, `score?`, `children_count`.

`LiveChildOutput`: `id`, `module` (string), `started_at`, `ended_at?`, `duration_ms?`, `score?`, `status`.

`LiveMetricsOutput`: `stop_reason`.

`LiveSessionDetail`: `id`, `user_id`, `started_at`, `ended_at?`, `duration_ms?`, `score?`, `status`, `created_at`, `metrics?`, `children` (lista ordenada por started_at).

`LiveSessionListItem`: id + timeline meta + `children_count` + `stop_reason?` (NULL si aún active).

## 5. Casos de uso (`sessions.py`)

- `start_live_session(db, user)`: inserta sessions(active). Retorna fila.
- `finalize_live_session(db, user, session_id)`: valida active, computa avg score, marca completed con `live_metrics(stop_reason='completed')`.
- `abandon_live_session(db, user, session_id, stop_reason)`: igual pero status=aborted con stop_reason del cliente. Defensive guard contra stop_reason='completed'.
- `list_live_sessions(db, user)`: query con subselect correlacionado para `children_count` + LEFT JOIN a live_metrics para `stop_reason`.
- `get_live_session(db, user, session_id)`: detalle con children list. None para no-encontrado o cross-user → router 404.

### Helpers privados

- `_load_active_live_session(db, user, session_id) -> Session`: load + validate ownership + status, lanza excepciones tipadas.
- `_avg_completed_children_score(db, parent_id) -> int | None`: promedio Postgres AVG ignorando NULLs, filtrando por `status='completed'`.

## 6. Endpoints

- `POST /live/sessions` → 201 `StartSessionResponse`.
- `POST /live/sessions/{id}/finalize` → 200 `FinalizeSessionResponse` / 404 / 409.
- `PATCH /live/sessions/{id}/abandon` (body: `AbandonSessionRequest`) → 204 / 404 / 409 / 422 (stop_reason='completed').
- `GET /live/sessions` → 200 lista todas las status.
- `GET /live/sessions/{id}` → 200 / 404.

Todos requieren Bearer JWT.

## 7. Pendientes en el roadmap

- **Wiring de `parent_id` en los 11 módulos componentes**: hoy todos los `create_<modulo>_session` hardcodean `parent_id=None`. Para que la composición funcione end-to-end, cada uno debe aceptar `parent_id` opcional, validar que sea de una live `active` del mismo user, y persistir el hijo con esa referencia. ~9 módulos x ~30min = una vuelta entera; cada uno es un commit chico con patrón claro.
- **Frontend**: actualizar el flujo "sesión libre" para usar el nuevo lifecycle HTTP (start → modules con parent_id → finalize/abandon) en lugar del viejo WebSocket multi-dim.
- **Streaming multi-dim**: si se quiere re-introducir el análisis simultáneo de múltiples dimensiones sobre un mismo audio (feature del live viejo), implementar como módulo independiente que persista hijos con parent_id apuntando a la live actual. NO mezclar con este orquestador.
- **`stop_reason` en otros módulos**: solo live_metrics tiene la columna. Si las analytics necesitan distinguir reasons en otros módulos (fluency time_limit vs disconnect, por ejemplo), agregar columna análoga.
