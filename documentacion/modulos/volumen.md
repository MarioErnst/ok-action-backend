# Volumen (Loudness Coach) — Documentación Backend

## 1. Descripción funcional

El módulo de Volumen (Loudness Coach) permite a los usuarios monitorear y mejorar la intensidad acústica de su voz durante sesiones de entrenamiento. El usuario selecciona o crea un preset de contexto que define umbrales de decibeles para diferentes bandas acústicas según el escenario (conferencia, clase, conversación normal, etc.).

El análisis acústico en tiempo real se realiza en el frontend mediante Web Audio API. El backend gestiona dos aspectos principales:

1. **Gestión de presets**: define los umbrales acústicos de cada contexto. Incluye presets del sistema (no editables, visibles para todos los usuarios) y presets personalizados del usuario (editables, privados).
2. **Persistencia de sesiones**: almacena las sesiones completadas con sus métricas agrupadas por banda acústica, permitiendo análisis histórico del desempeño.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| **Presentación (Router)** | `backend/app/presentation/routers/loudness.py` | Define los endpoints HTTP, valida requests, mapea respuestas. |
| **Esquemas** | `backend/app/presentation/schemas/loudness.py` | Define estructuras de datos para solicitudes y respuestas. |
| **Casos de uso** | `backend/app/use_cases/loudness/` | Orquesta la lógica de negocio (presets.py, sessions.py). |
| **Entidades** | `backend/app/domain/entities/` | Modelos de dominio: `loudness_preset.py`, `loudness_session.py`. |

## 3. Modelo de datos

### Tabla: `loudness_presets`

Almacena los presets de contexto acústico, tanto del sistema como personalizados del usuario.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único del preset. |
| `user_id` | UUID | FK → users (CASCADE) \| NULL | Propietario. NULL indica preset del sistema (no editable). |
| `label` | VARCHAR(100) | NOT NULL | Nombre del preset (ej: "Conferencia", "Clase Online"). |
| `description` | TEXT | nullable | Descripción opcional del contexto. |
| `silence_offset_db` | NUMERIC(6,2) | NOT NULL | Umbral de silencio en dB (relativo al noise floor). |
| `too_low_offset_db` | NUMERIC(6,2) | NOT NULL | Umbral inferior de volumen demasiado bajo. |
| `optimal_offset_db` | NUMERIC(6,2) | NOT NULL | Centro del rango óptimo de volumen. |
| `clip_threshold_dbfs` | NUMERIC(6,2) | NOT NULL | Umbral de clipping (saturación) en dBFS. |
| `is_default` | BOOLEAN | NOT NULL | Si es el preset seleccionado por defecto para el usuario. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp de creación. |

### Tabla: `loudness_sessions`

Registra las sesiones de entrenamiento completadas con métricas acústicas agregadas.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la sesión. |
| `user_id` | UUID | FK → users (CASCADE) | Usuario propietario. |
| `preset_id` | UUID | FK → loudness_presets (SET NULL) | Preset utilizado. Se pone NULL si el preset se elimina. |
| `duration_ms` | INTEGER | NOT NULL | Duración total de la sesión en milisegundos. |
| `optimal_percent` | NUMERIC(5,2) | NOT NULL | Porcentaje de tiempo dentro de banda óptima (0-100). |
| `peak_db` | NUMERIC(8,2) | NOT NULL | Pico máximo de volumen detectado en dB. |
| `band_time_ms` | JSONB | NOT NULL | Tiempo en ms por banda: `{silence, too-low, optimal, too-high, clipping}`. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp de creación. |

### Migración

Las tablas se crean en `0c400000111e_initial_schema.py`, junto con el esquema inicial de fonación.

## 4. Esquemas de solicitud y respuesta

### `LoudnessPresetResponse`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | Identificador del preset. |
| `label` | str | Nombre del preset. |
| `description` | str \| None | Descripción opcional. |
| `silence_offset_db` | float | Umbral de silencio. |
| `too_low_offset_db` | float | Umbral de volumen bajo. |
| `optimal_offset_db` | float | Umbral de volumen óptimo. |
| `clip_threshold_dbfs` | float | Umbral de clipping. |
| `is_default` | bool | Si es el preset por defecto. |

### `LoudnessPresetCreateRequest`

Igual a `LoudnessPresetResponse` sin `id` ni `is_default`. El campo `description` es opcional.

### `LoudnessPresetUpdateRequest`

Todos los campos de `LoudnessPresetCreateRequest` son opcionales. Solo se actualizan los campos presentes en la solicitud.

### `LoudnessSessionRequest`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `preset_id` | UUID | Preset utilizado en la sesión. |
| `duration_ms` | int | Duración en milisegundos. |
| `optimal_percent` | float | Porcentaje de tiempo en rango óptimo. |
| `peak_db` | float | Pico máximo de volumen. |
| `band_time_ms` | dict | Tiempo en ms por banda acústica. |

### `LoudnessSessionResponse`

Igual al request más `id` y `created_at`.

### `LoudnessSessionListItem`

Respuesta compacta: `id`, `preset_id`, `optimal_percent`, `duration_ms`, `created_at`.

## 5. Casos de uso

### `list_presets(user, session)`

Retorna presets con `user_id IS NULL` (presets del sistema) más los presets del usuario actual, ordenados por `is_default DESC`, `label ASC`.

### `create_preset(data, user, session)`

Crea un `LoudnessPreset` con `is_default=False` y el `user_id` del usuario actual.

### `update_preset(preset_id, data, user, session)`

Verifica que el preset pertenezca al usuario (los presets del sistema, `user_id IS NULL`, no son editables). Actualiza solo los campos no-None del request. Hace commit.

**Errores:** 403 Forbidden si el preset es del sistema o pertenece a otro usuario.

### `delete_preset(preset_id, user, session)`

Verifica propiedad, elimina el registro y hace commit. Las sesiones asociadas recibirán `preset_id = NULL` por la política `SET NULL` de la clave foránea.

**Errores:** 403 Forbidden si el preset es del sistema o pertenece a otro usuario.

### `save_loudness_session(data, user, session)`

Crea un `LoudnessSession` con los datos del request y el `user_id` del usuario actual.

### `list_loudness_sessions(user, session)`

Consulta las sesiones del usuario ordenadas por `created_at` descendente.

## 7. Endpoints de la API

### GET `/loudness/presets`

Obtiene todos los presets accesibles (sistema + propios del usuario).

- **Autenticación:** Bearer token requerido
- **Respuesta (200 OK):** `list[LoudnessPresetResponse]`

---

### POST `/loudness/presets`

Crea un nuevo preset personalizado.

- **Método:** POST — **Código:** 201 Created
- **Body:** `LoudnessPresetCreateRequest`
- **Respuesta:** `LoudnessPresetResponse`

---

### PUT `/loudness/presets/{preset_id}`

Actualiza un preset personalizado existente.

- **Respuesta (200 OK):** `LoudnessPresetResponse`
- **Errores:** `403` — preset del sistema o no pertenece al usuario. `404` — no existe.

---

### DELETE `/loudness/presets/{preset_id}`

Elimina un preset personalizado.

- **Respuesta:** 204 No Content (sin body)
- **Errores:** `403` — preset del sistema o no pertenece al usuario.

---

### POST `/loudness/sessions`

Guarda una sesión de entrenamiento completada.

- **Código:** 201 Created
- **Body:** `LoudnessSessionRequest`
- **Respuesta:** `LoudnessSessionResponse`

---

### GET `/loudness/sessions`

Lista todas las sesiones del usuario autenticado en orden descendente.

- **Respuesta (200 OK):** `list[LoudnessSessionListItem]`
