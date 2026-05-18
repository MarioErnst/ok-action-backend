# Sesión Live (Composición) — Documentación Backend

> Detección en tiempo real durante la sesión vía Gemini Live (function
> calling, WS bidireccional) documentada en
> [`live-strike-system.md`](./live-strike-system.md). El endpoint
> `evaluate-frame` y el pipeline frame-by-frame fueron eliminados; los
> strikes ahora viajan por la WS de live streaming. Este archivo cubre el
> lifecycle de composición y el composed eval final, que siguen igual.

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
- `POST /live/sessions/{id}/audio-evaluation` → 200 `ComposedAudioEvaluationResponse` / 422 / 502.
- `GET /live/sessions` → 200 lista todas las status.
- `GET /live/sessions/{id}` → 200 / 404.

Todos requieren Bearer JWT.

## 7. Endpoint de evaluación compuesta de audio

`POST /live/sessions/{id}/audio-evaluation` agrupa la evaluación de hasta cuatro módulos sobre un único audio en una sola llamada a Gemini. Reemplaza el flujo viejo del WebSocket multi-dim sin reintroducir streaming: el cliente graba localmente con `MediaRecorder`, y al cierre envía el blob junto con la lista de módulos seleccionados.

### Contrato

Multipart `POST /live/sessions/{id}/audio-evaluation` con campos:

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `audio` | UploadFile | sí | Blob del MediaRecorder (`audio/webm` en Chrome/Android, `audio/mp4` en iOS Safari). |
| `modules` | repeated form (`modules=muletillas&modules=phonation`) | sí | Subconjunto no vacío de `{muletillas, facial_expression, phonation, loudness}`. |
| `started_at` | datetime ISO | sí | Timestamp del cliente cuando comenzó la captura. El backend confía porque sólo afecta a la duración propia del usuario. |
| `prompt_text` | string | no | Consigna libre (opcional). Se incluye como contexto en el prompt compuesto. |
| `facial_summary` | JSON string | si `facial_expression` en `modules` | Siete porcentajes de emociones (`happy_pct`...`neutral_pct`) computados en cliente. |
| `phonation_summary` | JSON string | si `phonation` en `modules` | `{avg_hz, stability_score, breaks_count}` computado client-side desde el AudioWorklet. |
| `loudness_summary` | JSON string | si `loudness` en `modules` | `{preset_id, optimal_pct, low_pct, high_pct, clipping_pct, peak_db, noise_floor_db}` computado client-side. |

Respuesta `200 ComposedAudioEvaluationResponse`:

```json
{
  "audio_intelligible": true,
  "children": [{ "id": "...", "module": "muletillas", "score": 78, ... }, ...],
  "evaluation": { "audio_intelligible": true, "muletillas": {...}, ... }
}
```

Códigos de error:
- `422` si `modules` está vacío, contiene un módulo no componible, el `parent_id` no apunta a una live activa del usuario, o el audio viene vacío.
- `502` si Gemini no respondió o devolvió JSON inválido (caller decide reintento o avisar al usuario).

Cuando `audio_intelligible=false`, el endpoint responde `200` pero `children` es `[]` y no se persiste ningún hijo: la live sigue válida y `finalize` agregará score=NULL.

### Flujo interno

1. Validación de `modules` (no vacío, todos en la enum interna `ComposableModule`).
2. `validate_parent_live_session(db, user, session_id)` → `InvalidParentLiveError` se mapea a 422.
3. `audio.read()` y `mime_type = audio.content_type` (defaultea a `audio/webm`).
4. `evaluate_composed_audio(audio_bytes, mime_type, modules, prompt_text)` arma prompt+schema dinámicos y llama a Gemini una sola vez.
5. `persist_composed_evaluation(...)` crea N hijos `Session(module=<modulo>, parent_id=<live_id>, status='completed')` + sus filas `<modulo>_metrics` correspondientes. Si `audio_intelligible=false`, no persiste nada.
6. Respuesta con la lista de hijos creados + el dict de Gemini para que el cliente renderice el summary sin GETs adicionales.

### Capas

| Archivo | Responsabilidad |
|---------|-----------------|
| `app/use_cases/live/composed/prompts.py` | Secciones de prompt por módulo + `build_composed_prompt`. |
| `app/use_cases/live/composed/schemas.py` | Secciones de JSON schema por módulo + `build_composed_schema`. |
| `app/use_cases/live/composed/persist.py` | Toma el dict de Gemini y persiste N hijos + métricas. |
| `app/infrastructure/ai/composed_live_gemini.py` | Llama a Gemini con audio + prompt + schema unificados. |
| `app/presentation/routers/live.py` | Endpoint multipart, validación, orquestación, respuesta. |

### Decisiones de diseño

- **Composable set actual**: `muletillas`, `facial_expression`, `phonation`, `loudness`. `accentuation` y `pronunciation` fueron retirados del set componible de live a favor de los dos client-side modules que cuestan cero llamadas a Gemini y tienen latencia mínima. Los módulos standalone de pron/acc siguen intactos en sus páginas dedicadas.
- **Gemini solo evalúa muletillas**: los otros tres se computan 100% en el navegador y submiten su `*_summary` como JSON en la request. El endpoint short-circuitea la llamada a Gemini cuando ninguno de los módulos seleccionados es evaluable por audio (`AUDIO_COMPOSABLE_MODULES`).
- **Prompts y schemas separados por módulo**: cada sección Gemini se mantiene como constante privada. El composer arma la unión según los módulos seleccionados.
- **Orden determinístico**: tanto el prompt como el schema ordenan los módulos según `VALID_MODULES`. Inputs equivalentes producen prompts idénticos.
- **Versión "live" del prompt distinta de la standalone**: muletillas standalone asume `question_text`; live es habla libre. Las dos versiones cubren productos diferentes.
- **Score del child phonation = stability_score**: replica el patrón del módulo standalone. `exercises_count=0` porque la live es una sola grabación, no una serie de ejercicios.
- **Score del child loudness = optimal_pct**: porcentaje del tiempo dentro de la banda óptima. Los cuatro pcts son re-normalizados server-side para garantizar suma=100 (BD CHECK constraint).
- **`preset_id` obligatorio para loudness**: la tabla referencia `loudness_presets` por FK. Si el cliente no manda preset_id, ese child se omite (no se inventa default).
- **Live finalize compatible sin cambios**: `_avg_completed_children_score` ya promediaba sobre hijos `completed` con `score IS NOT NULL`, así que cualquier hijo creado por el endpoint de audio-evaluation entra automáticamente al cálculo agregado.
- **No mínimo de bytes**: dejar la decisión de "hay habla suficiente" a Gemini vía `audio_intelligible`. Distintos codecs tienen bitrates muy distintos, y un threshold fijo en bytes daría falsos negativos en algunas plataformas.
- **`gemini_response` se devuelve crudo al cliente**: el frontend tiene la información rica (feedback, muletillas detectadas, etc.) sin GETs adicionales, pero todo lo no persistido es ephemeral. Si en el futuro se quiere historial detallado del feedback, hay que crear tablas para esos campos.

## 8. Pendientes en el roadmap

- **Streaming multi-dim**: si se quiere re-introducir el análisis simultáneo en tiempo real durante la grabación (feature del live viejo, eliminada con la migración), implementar como módulo separado encima del modelo de composición. No mezclar con el orquestador HTTP actual.
- **`stop_reason` en otros módulos**: solo live_metrics tiene la columna. Si las analytics necesitan distinguir reasons en otros módulos (fluency time_limit vs disconnect, por ejemplo), agregar columna análoga.
- **Tests del endpoint de audio-evaluation**: la suite actual cubre el lifecycle HTTP base (start/finalize/abandon/list/get). Falta cubrir el endpoint compuesto con un mock de Gemini para validar el parser y la persistencia de hijos sin quemar cuota.
