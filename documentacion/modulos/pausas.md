# Pausas — Documentación Backend

## 1. Descripción funcional

El módulo de Pausas permite registrar y consultar sesiones donde el usuario practica el uso de silencios durante una respuesta oral. El objetivo no es penalizar toda pausa, sino distinguir entre pausas intencionales que ordenan el discurso, pocas pausas que vuelven el habla apresurada y demasiadas pausas que cortan la fluidez.

El flujo funcional de la modalidad normal es el siguiente:

1. El frontend presenta una consigna al usuario.
2. El usuario graba su respuesta.
3. El frontend analiza los frames de audio, detecta intervalos de silencio y calcula métricas de pausas.
4. El frontend envía las métricas ya calculadas al backend.
5. El backend valida el contrato, persiste la sesión y permite consultar el historial.

En esta modalidad normal, el backend no invoca Gemini AI. La evaluación se calcula en el cliente y el backend actúa como capa de persistencia autenticada.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| **Presentación (Router)** | `backend/app/presentation/routers/pauses.py` | Expone endpoints HTTP para crear, listar y consultar sesiones de pausas. |
| **Presentación (Schemas)** | `backend/app/presentation/schemas/pauses.py` | Define contratos Pydantic de métricas, intervalos y sesiones. |
| **Casos de uso** | `backend/app/use_cases/pauses/sessions.py` | Persiste sesiones y consulta sesiones del usuario autenticado. |
| **Entidades** | `backend/app/domain/entities/pause_session.py` | Modelo SQLAlchemy `PauseSession`. |
| **Migración** | `backend/alembic/versions/9a1c2f3d4e5f_add_pause_sessions.py` | Crea la tabla `pause_sessions`. |

## 3. Modelo de datos

### Tabla: `pause_sessions`

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la sesión. |
| `user_id` | UUID | FK → users (CASCADE), NOT NULL | Usuario propietario de la sesión. |
| `prompt_text` | VARCHAR(500) | NOT NULL | Consigna usada para la práctica. |
| `duration_ms` | INTEGER | NOT NULL | Duración total de la grabación en milisegundos. |
| `total_pauses` | INTEGER | NOT NULL | Cantidad de pausas detectadas. |
| `total_pause_duration_ms` | INTEGER | NOT NULL | Suma de duración de todas las pausas. |
| `average_pause_ms` | NUMERIC(10,2) | NOT NULL | Duración promedio de pausa. |
| `longest_pause_ms` | INTEGER | NOT NULL | Duración de la pausa más larga. |
| `silence_ratio` | NUMERIC(6,4) | NOT NULL | Proporción de silencio respecto de la duración total. |
| `classification` | VARCHAR(50) | NOT NULL | Clasificación: `pocas pausas`, `pausas adecuadas` o `demasiadas pausas`. |
| `pauses` | JSONB | NOT NULL | Lista de intervalos detectados. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Timestamp de creación. |

**Relación:** un usuario tiene muchas `pause_sessions` (1:N).

### Migración

Archivo: `backend/alembic/versions/9a1c2f3d4e5f_add_pause_sessions.py`

La migración depende de `177abcd602b1` y crea la tabla `pause_sessions`.

## 4. Esquemas de solicitud y respuesta

### `PauseInterval`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `start_ms` | int | Inicio del intervalo de pausa relativo al comienzo de la grabación. |
| `end_ms` | int | Fin del intervalo de pausa. |
| `duration_ms` | int | Duración del intervalo. |

Todos los campos deben ser mayores o iguales a 0.

### `PauseMetrics`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `total_pauses` | int | Cantidad de pausas detectadas. |
| `total_pause_duration_ms` | int | Duración acumulada de pausas. |
| `average_pause_ms` | float | Duración promedio de pausa. |
| `longest_pause_ms` | int | Pausa más larga detectada. |
| `silence_ratio` | float | Proporción entre 0 y 1 de silencio sobre duración total. |
| `classification` | str | Resultado cualitativo de la evaluación. |
| `pauses` | list[PauseInterval] | Intervalos individuales detectados. |

### `PauseSessionRequest`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `prompt_text` | str | Consigna usada por el usuario. Longitud: 1 a 500 caracteres. |
| `duration_ms` | int | Duración total de la grabación. Debe ser mayor a 0. |
| `pause_metrics` | PauseMetrics | Métricas calculadas por el frontend. |

### `PauseSessionResponse`

Respuesta completa de una sesión: `id`, `prompt_text`, `duration_ms`, `pause_metrics` y `created_at`.

### `PauseSessionListItem`

Respuesta compacta para historial: `id`, `prompt_text`, `duration_ms`, `total_pauses`, `silence_ratio`, `classification` y `created_at`.

## 5. Casos de uso

### `save_pause_session(data, user, session)`

Crea una entidad `PauseSession` con las métricas recibidas, asigna `user_id` al usuario autenticado, persiste la sesión y retorna el registro refrescado desde la base de datos.

La función no recalcula métricas ni reinterpreta la clasificación. Su responsabilidad es persistir el resultado validado por los schemas.

### `list_pause_sessions(user, session)`

Consulta todas las sesiones de pausas del usuario autenticado, ordenadas por `created_at` descendente.

### `get_pause_session(session_id, user, session)`

Busca una sesión por `session_id` y `user_id`. Al filtrar por ambos campos, evita devolver sesiones pertenecientes a otro usuario. Retorna `None` si no existe o no pertenece al usuario autenticado.

## 6. Integración con Gemini AI

La modalidad normal de pausas no utiliza Gemini AI en backend. La detección de pausas se calcula en frontend mediante análisis de frames de audio y se envía al backend como datos estructurados.

La integración con Gemini existe únicamente dentro de **Sesión Libre** cuando el usuario selecciona la dimensión `pause`. En ese flujo:

1. El frontend envía `pause` dentro de `dims` al WebSocket `/live/session`.
2. El backend valida `pause` como dimensión permitida.
3. `prompt_builder.py` agrega instrucciones para evaluar pausas sin marcarlas como negativas por defecto.
4. `live_gemini.py` exige un objeto `dims.pause` con score, métricas estimadas y clasificación.
5. El resultado queda guardado como parte de `live_sessions.analyses`, no como una fila en `pause_sessions`.

Ejemplo de respuesta esperada en sesión libre:

```json
{
  "dims": {
    "pause": {
      "sc": 84,
      "total_pauses": 3,
      "avg_pause_ms": 760,
      "longest_pause_ms": 1200,
      "silence_ratio": 0.18,
      "classification": "pausas adecuadas",
      "note": "Las pausas separan ideas sin cortar la fluidez."
    }
  },
  "overall": 84,
  "fb": "Buen uso de silencios para ordenar las ideas."
}
```

## 7. Endpoints de la API

### POST `/pauses/sessions`

Crea una nueva sesión de pausas persistiendo las métricas calculadas por el frontend.

- **Código:** 201 Created
- **Autenticación:** Bearer token requerido
- **Body:** `PauseSessionRequest`
- **Respuesta:** `PauseSessionResponse`

---

### GET `/pauses/sessions`

Lista las sesiones de pausas del usuario autenticado en orden descendente.

- **Autenticación:** Bearer token requerido
- **Respuesta:** `list[PauseSessionListItem]`

---

### GET `/pauses/sessions/{session_id}`

Obtiene el detalle completo de una sesión de pausas.

- **Autenticación:** Bearer token requerido
- **Parámetros de ruta:** `session_id`
- **Respuesta:** `PauseSessionResponse`
- **Errores:** `404` si la sesión no existe o no pertenece al usuario autenticado.
