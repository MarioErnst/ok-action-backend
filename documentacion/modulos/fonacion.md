# Fonación — Documentación Backend

## 1. Descripción funcional

El módulo de Fonación permite al usuario ejecutar ejercicios vocales (sostenido y deslizado) para mejorar su técnica vocal. Todo el análisis acústico ocurre en el frontend con Web Audio API: cálculo de frecuencia (Hz), estabilidad, conteo de quiebres y validación de rango esperado por ejercicio.

El backend recibe la sesión completa ya analizada y tiene dos responsabilidades:

1. Persistir la sesión y sus ejercicios bajo el esquema unificado de la base de datos.
2. Exponer el histórico de sesiones standalone del usuario.

No realiza procesamiento de audio ni cálculos derivados.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/phonation.py` | Endpoints HTTP, mapeo de errores y traducción a esquemas de respuesta. |
| Schemas | `backend/app/presentation/schemas/phonation.py` | Contratos Pydantic v2 de entrada y salida; validación de rangos y consistencia. |
| Use cases | `backend/app/use_cases/phonation/sessions.py` | Persistencia y consultas; orquesta la transacción multi-tabla. |
| Entidades | `backend/app/domain/entities/session.py`, `phonation_metrics.py`, `phonation_session_exercise.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

Una sesión de fonación se representa con tres filas relacionadas en el esquema uniforme.

### `sessions` (raíz, compartida con todos los módulos)

Una fila por sesión. Para fonación standalone, `module='phonation'` y `parent_id=NULL`. Cuando la sesión sea parte de una sesión live (futuro módulo `live`), `parent_id` apuntará a la fila de tipo `live`.

Columnas relevantes para fonación:

- `id UUID PK`
- `user_id UUID FK users(id) ON DELETE CASCADE`
- `module module_enum NOT NULL` (`phonation`)
- `parent_id UUID NULL FK sessions(id) ON DELETE CASCADE`
- `started_at TIMESTAMPTZ NOT NULL`
- `ended_at TIMESTAMPTZ NOT NULL` (siempre presente porque al postear la sesión ya está completa)
- `duration_ms INT NOT NULL` (derivado por backend desde `ended_at - started_at`)
- `score SMALLINT 0-100`
- `status session_status_enum NOT NULL` (`completed` para sesiones posteadas; `aborted` queda reservado para el orquestador live)

### `phonation_metrics` (1:1 con `sessions`)

Métricas agregadas de la sesión.

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1 con la fila de `sessions`. |
| `avg_hz` | NUMERIC(8,2) | NOT NULL | Frecuencia promedio en Hz de toda la sesión. |
| `stability_score` | SMALLINT | NOT NULL, CHECK 0-100 | Estabilidad agregada (0-100). |
| `breaks_count` | INT | NOT NULL DEFAULT 0 | Total de quiebres vocales detectados. |
| `exercises_count` | INT | NOT NULL DEFAULT 0 | Cantidad de ejercicios incluidos en la sesión. |

### `phonation_session_exercises` (N:1 con `sessions`)

Una fila por tipo de ejercicio dentro de la sesión. Permite agregados longitudinales por `exercise_type` (ej. evolución de estabilidad en `gliding` a lo largo del tiempo).

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK compuesta + FK `sessions.id` ON DELETE CASCADE | Sesión a la que pertenece. |
| `exercise_type` | exercise_type_enum | PK compuesta | `holding` o `gliding`. PK compuesta `(session_id, exercise_type)` evita duplicados. |
| `avg_hz` | NUMERIC(8,2) | NOT NULL | Frecuencia promedio del ejercicio. |
| `stability_score` | SMALLINT | NOT NULL, CHECK 0-100 | Estabilidad del ejercicio. |
| `breaks_count` | INT | NOT NULL DEFAULT 0 | Quiebres del ejercicio. |
| `in_range_pct` | SMALLINT | NOT NULL, CHECK 0-100 | Porcentaje de tiempo dentro del rango objetivo. |

### Decisiones de diseño

- **Sin `observations`**: el campo `observations JSONB` del esquema viejo se descartó intencionalmente. Era texto libre sin estructura aprovechable analíticamente.
- **Sin `exercise_id`**: se eliminó el identificador puntual del ejercicio. El catálogo de ejercicios variaba poco y no se usaba en queries longitudinales; lo que sí tenía valor era el tipo (`holding` / `gliding`), que ahora vive como enum.
- **`in_range` ahora es `in_range_pct` (0-100)** en vez de `boolean`. Captura la calidad real del ejercicio, no solo si pasó el umbral.
- **PK compuesta `(session_id, exercise_type)`** en `phonation_session_exercises`: garantiza una sola fila por tipo dentro de una sesión. Si en el futuro se permite repetir un ejercicio en la misma sesión, hay que cambiar a una PK sintética.
- **`duration_ms` derivado en backend**: el cliente envía `started_at` y `ended_at`; el backend calcula la duración. Evita confiar en valores derivables que el cliente podría falsear o desincronizar.

## 4. Esquemas de solicitud y respuesta

### Entrada

`PhonationSessionCreate`:

| Campo | Tipo | Reglas |
|-------|------|--------|
| `started_at` | datetime | Debe ser `< ended_at`. |
| `ended_at` | datetime | — |
| `score` | int | 0-100. |
| `metrics` | `PhonationMetricsInput` | Ver abajo. |
| `exercises` | list[`PhonationExerciseInput`] | Mínimo 1, sin `exercise_type` repetido. `metrics.exercises_count` debe igualar `len(exercises)`. |

`PhonationMetricsInput`: `avg_hz` (>0), `stability_score` (0-100), `breaks_count` (>=0), `exercises_count` (>=1).

`PhonationExerciseInput`: `exercise_type` (`"holding"` o `"gliding"`), `avg_hz` (>0), `stability_score` (0-100), `breaks_count` (>=0), `in_range_pct` (0-100).

### Salida

`PhonationSessionDetail`: `id`, `user_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`, `metrics`, `exercises`.

`PhonationSessionListItem` (compacto): `id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `avg_hz`. Suficiente para renderizar una tarjeta de timeline sin pegarle al endpoint de detalle.

## 5. Casos de uso

### `create_phonation_session(db, user, payload)`

Inserta tres filas en una sola transacción:

1. Una fila en `sessions` con `module='phonation'`, `status='completed'`, `parent_id=NULL`, `duration_ms` derivado.
2. Una fila en `phonation_metrics` (1:1) con las métricas agregadas.
3. N filas en `phonation_session_exercises` (una por `exercise_type`).

Si cualquier insert falla, la transacción se hace rollback completa. Retorna la tupla `(session_row, metrics_row, exercise_rows)` lista para mapear a la respuesta.

### `list_phonation_sessions(db, user)`

Hace JOIN entre `sessions` y `phonation_metrics`, filtra `module='phonation'` y `parent_id IS NULL` (excluye las que son hijas de un live), ordena por `started_at DESC`. El filtro por `parent_id` es clave: las sesiones nested en un live se exponen a través del histórico del módulo `live`, no del de fonación.

### `get_phonation_session(db, user, session_id)`

Detalle completo. Carga la sesión, valida ownership comparando `user_id`, luego carga `phonation_metrics` y los `phonation_session_exercises` ordenados por `exercise_type`. Retorna `None` si no existe **o** si pertenece a otro usuario; el router mapea `None` a HTTP 404 sin distinguir entre ambos casos para no filtrar información de existencia.

## 6. Endpoints

### `POST /phonation/sessions`

Crea una nueva sesión de fonación.

- Auth: Bearer JWT.
- Status: `201 Created`.
- Body: `PhonationSessionCreate`.
- Respuesta: `PhonationSessionDetail`.
- Errores:
  - `401` token ausente o inválido.
  - `422` validación fallida (rangos, `ended_at <= started_at`, `exercises_count` inconsistente, `exercise_type` duplicado, lista vacía).

### `GET /phonation/sessions`

Histórico standalone del usuario.

- Auth: Bearer JWT.
- Status: `200 OK`.
- Respuesta: `list[PhonationSessionListItem]`, ordenado por `started_at DESC`.
- Lista vacía si no hay sesiones.

### `GET /phonation/sessions/{session_id}`

Detalle de una sesión.

- Auth: Bearer JWT.
- Status: `200 OK`.
- Respuesta: `PhonationSessionDetail`.
- Errores:
  - `401` token ausente o inválido.
  - `404` la sesión no existe o pertenece a otro usuario (no se distingue para no filtrar ownership).

## 7. Pendientes en el roadmap

- **Composición en sesión live**: cuando se reescriba el módulo `live`, `create_phonation_session` debe aceptar un `parent_id` opcional para asociar la fila a la sesión live padre. En ese momento también el endpoint POST puede exponer `parent_id` o quedarse oculto y permitir que solo el orquestador live lo invoque internamente.
- **Sesiones abortadas**: hoy el endpoint solo persiste `status='completed'`. Si se quiere registrar abandonos parciales en standalone, hay que agregar un endpoint `PATCH /phonation/sessions/{id}/abort` o similar.
