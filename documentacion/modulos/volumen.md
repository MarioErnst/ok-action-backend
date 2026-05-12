# Volumen (Loudness Coach) — Documentación Backend

## 1. Descripción funcional

El módulo de Volumen permite al usuario monitorear y mejorar la intensidad acústica de su voz. Se basa en dos conceptos: **presets** (perfiles de calibración del micrófono que definen umbrales de dB para cada escenario) y **sesiones** (la grabación de un entrenamiento contra un preset, con la distribución del tiempo en cada banda acústica).

El análisis en tiempo real se hace en el frontend con Web Audio API. El backend tiene dos responsabilidades:

1. **Presets**: lista, crea, edita y borra perfiles. Hay presets globales del sistema (visibles para todos, no editables) y presets personales del usuario.
2. **Sesiones**: persiste sesiones completadas y devuelve el histórico standalone.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/loudness.py` | Endpoints HTTP, mapeo de errores, traducción a esquemas. |
| Schemas | `backend/app/presentation/schemas/loudness.py` | Contratos Pydantic v2 con validación de rangos y suma de bandas. |
| Use cases | `backend/app/use_cases/loudness/presets.py`, `sessions.py` | Lógica de presets (CRUD) y sesiones (transacción multi-tabla). |
| Entidades | `backend/app/domain/entities/loudness_preset.py`, `loudness_metrics.py`, `session.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

### `loudness_presets`

Perfiles de calibración del micrófono. `user_id IS NULL` denota un preset global.

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `id` | UUID | PK | — |
| `user_id` | UUID | NULL FK `users.id` ON DELETE CASCADE | NULL = preset global del sistema. |
| `label` | VARCHAR(100) | NOT NULL | Nombre visible del preset. |
| `description` | TEXT | NULL | Descripción opcional. |
| `silence_offset_db` | NUMERIC(6,2) | NOT NULL | Offset de silencio sobre el ruido base. |
| `low_offset_db` | NUMERIC(6,2) | NOT NULL | Umbral inferior de la banda baja. |
| `optimal_offset_db` | NUMERIC(6,2) | NOT NULL | Umbral para considerar la banda como óptima. |
| `clip_threshold_db` | NUMERIC(6,2) | NOT NULL | Umbral de clipping (saturación). |
| `is_default` | BOOLEAN | NOT NULL DEFAULT FALSE | Marca presets seed-time prioritarios para la UI. |
| `created_at` | TIMESTAMPTZ | NOT NULL | — |

Los 3 presets globales (`Conversación`, `Presentación grupal`, `Auditorio grande`) los inserta el seed con `user_id NULL` e `is_default=TRUE`.

### `sessions` (raíz, compartida)

Una fila por sesión. Para loudness standalone: `module='loudness'`, `parent_id=NULL`. Cuando se reescriba el módulo `live`, las sesiones nested usarán `parent_id=<live_id>`.

Columnas relevantes:

- `id`, `user_id`, `module='loudness'`, `parent_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`.
- `score` aquí es **derivado por backend = `optimal_pct`** (ver decisiones de diseño).

### `loudness_metrics` (1:1 con `sessions`)

Métricas agregadas de la sesión.

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `preset_id` | UUID | NOT NULL FK `loudness_presets.id` ON DELETE RESTRICT | El preset usado en esa sesión. RESTRICT impide borrar presets referenciados. |
| `optimal_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % del tiempo en banda óptima. |
| `low_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % del tiempo en banda baja. |
| `high_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % del tiempo en banda alta. |
| `clipping_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % del tiempo en clipping. |
| `peak_db` | NUMERIC(8,2) | NOT NULL | dB pico de la sesión. |

CHECK adicional: `optimal_pct + low_pct + high_pct + clipping_pct = 100`.

### Decisiones de diseño

- **`band_time_ms JSONB` reemplazado por 4 columnas `_pct`**: el JSONB del esquema viejo no era queryable longitudinalmente. Cuatro SMALLINT con CHECK de suma=100 capturan la misma información de forma estructurada.
- **`score` se deriva en backend = `metrics.optimal_pct`**. Diferencia explícita con phonation: ahí el score es una fórmula compuesta multi-ejercicio que vive en frontend; aquí el score es literalmente el `optimal_pct`. Derivar en backend evita que cliente mande dos valores que pueden quedar desincronizados (mismo principio que `duration_ms`). **Convención general**: si la fórmula del score es trivial y única, derívalo en backend; si es compuesta y subjetiva, recíbelo del cliente.
- **`too_low_offset_db` → `low_offset_db`** y **`clip_threshold_dbfs` → `clip_threshold_db`**: nombres alineados con el resto del schema (sufijo `_db` consistente, sin abreviaciones tipo "dbfs").
- **Presets globales no editables**: `update_preset` y `delete_preset` filtran por `user_id == user.id`, así que los globales (`user_id IS NULL`) nunca matchean y devuelven None → router retorna 404.
- **FK RESTRICT** en `loudness_metrics.preset_id`: borrar un preset referenciado por sesiones provoca `IntegrityError` que el use_case captura como `PresetReferencedError` → router retorna 409.
- **Validación de preset en sesión**: `create_loudness_session` carga el preset y verifica que sea global o del usuario antes de insertar la fila. Si no, lanza `PresetNotAvailableError` → 422 (es un payload inválido, no autorización sobre un recurso hermano).
- **Endpoint nuevo `GET /loudness/sessions/{id}`**: el módulo viejo no tenía detalle de sesión, solo lista. El nuevo lo añade para consistencia con phonation y para que la UI pueda mostrar la página de detalle de una sesión histórica.

## 4. Esquemas

### Presets

`LoudnessPresetCreate`: `label` (1-100 chars), `description?`, `silence_offset_db`, `low_offset_db`, `optimal_offset_db`, `clip_threshold_db`.

`LoudnessPresetUpdate`: todos los anteriores opcionales (PATCH semántico vía `model_dump(exclude_unset=True)`).

`LoudnessPresetOutput`: campos del preset + `is_default` (de seed) + `is_global` (`user_id IS NULL`). El frontend usa `is_global` para deshabilitar botones de edit/delete.

### Sesiones

`LoudnessMetricsInput`: `preset_id`, `optimal_pct`, `low_pct`, `high_pct`, `clipping_pct` (cada uno 0-100), `peak_db`. Validador: las 4 bandas deben sumar 100.

`LoudnessSessionCreate`: `started_at`, `ended_at`, `metrics`. Validador: `ended_at > started_at`. **No incluye `score`**: el backend lo deriva.

`LoudnessSessionDetail`: `id`, `user_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`, `metrics`.

`LoudnessSessionListItem`: compacto para timeline → `id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `optimal_pct`, `preset_id`. Incluye `optimal_pct` y `preset_id` para que la card de timeline pueda renderizar sin pegarle al detalle.

## 5. Casos de uso

### Presets — `presets.py`

- `list_presets(db, user)`: globales + del usuario, ordenados por `is_default DESC, label`.
- `create_preset(db, user, payload)`: crea preset personal con `user_id=user.id`, `is_default=False`.
- `update_preset(db, user, preset_id, payload)`: PATCH de campos provistos. Filtro por `user_id` evita tocar globales y presets de otros.
- `delete_preset(db, user, preset_id)`: elimina preset propio. Si la FK RESTRICT lo bloquea, lanza `PresetReferencedError`.

### Sesiones — `sessions.py`

- `_resolve_preset(db, user, preset_id)`: helper privado. Valida que el preset sea global o del usuario; lanza `PresetNotAvailableError` si no. Permite que `create_loudness_session` falle temprano antes de tocar `sessions`/`loudness_metrics`.
- `create_loudness_session(db, user, payload)`: en una transacción, valida el preset, calcula `duration_ms` y `score=optimal_pct`, inserta `sessions` (`module='loudness'`, `status='completed'`, `parent_id=NULL`) y `loudness_metrics`.
- `list_loudness_sessions(db, user)`: JOIN sessions + metrics, filtra `module='loudness'` y `parent_id IS NULL`, ordena por `started_at DESC`. El filtro por `parent_id` excluye sesiones que sean parte de un live.
- `get_loudness_session(db, user, session_id)`: detalle. Retorna `None` para no-encontrado o cross-user (router → 404 sin distinguir, no se filtra existencia).

## 6. Endpoints

### Presets

- `GET /loudness/presets` → 200, `list[LoudnessPresetOutput]`. Globales + del usuario.
- `POST /loudness/presets` → 201, `LoudnessPresetOutput`. Crea preset personal.
- `PUT /loudness/presets/{id}` → 200 / 404. PATCH semántico.
- `DELETE /loudness/presets/{id}` → 204 / 404 / 409. 409 si está referenciado por sesiones.

### Sesiones

- `POST /loudness/sessions` → 201 / 422 (payload inválido o preset no disponible).
- `GET /loudness/sessions` → 200, lista standalone, ordenada por `started_at DESC`.
- `GET /loudness/sessions/{id}` → 200 / 404 (no existe o pertenece a otro usuario).

Todos los endpoints requieren Bearer JWT.

## 7. Pendientes en el roadmap

- **Composición en sesión live**: cuando se reescriba `live`, `create_loudness_session` debe aceptar `parent_id` opcional para encadenar la fila a una sesión live padre. El score y métricas se siguen calculando igual.
- **Sesiones abortadas**: hoy solo se persiste `status='completed'`. Aborted queda para el lifecycle del módulo `live`.
- **Validar combinaciones de offsets en presets**: hoy se aceptan tres `_offset_db` y un `_threshold_db` sin verificar que sean coherentes entre sí (p.ej. `low < optimal < clip`). Si surge un bug por presets mal configurados, agregar un `model_validator` en `LoudnessPresetCreate`/`Update`.
