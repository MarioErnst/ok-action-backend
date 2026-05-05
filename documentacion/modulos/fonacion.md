# Fonación — Documentación Backend

## 1. Descripción funcional

El módulo de Fonación permite al usuario seleccionar y ejecutar ejercicios vocales para mejorar su técnica vocal. Los ejercicios disponibles incluyen resonancia, estabilidad vocal y rango de tono.

El análisis acústico de los ejercicios se realiza completamente en el frontend utilizando Web Audio API. El frontend captura y procesa el audio del usuario, calculando métricas como frecuencia (Hz), amplitud (dB) por frame, estabilidad, presencia de quiebres vocales y validación de rango esperado.

El backend recibe exclusivamente los resultados ya calculados por el frontend y tiene dos responsabilidades:
1. Persistir las sesiones de fonación y sus ejercicios asociados en la base de datos.
2. Retornar el histórico de sesiones al usuario cuando lo solicita.

No se realiza procesamiento de audio, análisis de patrones complejos ni cálculos derivados en el backend.

## 2. Capas del módulo

El módulo Fonación sigue la arquitectura de capas definida en el proyecto:

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| **Presentación (Router)** | `backend/app/presentation/routers/phonation.py` | Define los endpoints HTTP, valida el formato de las solicitudes, transforma respuestas a JSON. |
| **Presentación (Schemas)** | `backend/app/presentation/schemas/phonation.py` | Define contratos de solicitud y respuesta con validación de tipos. |
| **Casos de uso** | `backend/app/use_cases/phonation/sessions.py` | Orquesta la lógica de persistencia y consulta de sesiones de fonación. |
| **Dominio (Entidades)** | `backend/app/domain/entities/phonation_session.py` | Define la entidad `PhonationSession` con sus atributos y relaciones. |
| **Dominio (Entidades)** | `backend/app/domain/entities/exercise_result.py` | Define la entidad `ExerciseResult` con sus atributos. |

La separación de responsabilidades garantiza que el router únicamente traduce HTTP, los schemas validan datos, los casos de uso orquestan operaciones de base de datos, y las entidades representan conceptos del dominio sin conocer detalles de persistencia.

## 3. Modelo de datos

### Tabla `phonation_sessions`

Almacena las sesiones de fonación completadas por los usuarios.

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `id` | UUID | PRIMARY KEY | Identificador único de la sesión. |
| `user_id` | UUID | FOREIGN KEY → `users.id` ON DELETE CASCADE | Usuario que realizó la sesión. |
| `overall_score` | NUMERIC(5,2) | NOT NULL | Puntuación general de la sesión (0 a 100). |
| `avg_hz` | NUMERIC(8,2) | NOT NULL | Frecuencia promedio (Hz) detectada en la sesión. |
| `observations` | JSONB | NOT NULL | Lista de observaciones o notas generadas durante la sesión. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Fecha y hora de creación de la sesión. |

**Relación:** una `phonation_session` tiene muchos `exercise_results`.

### Tabla `exercise_results`

Almacena los resultados individuales de cada ejercicio dentro de una sesión de fonación.

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `id` | UUID | PRIMARY KEY | Identificador único del resultado del ejercicio. |
| `session_id` | UUID | FOREIGN KEY → `phonation_sessions.id` ON DELETE CASCADE | Sesión a la que pertenece este resultado. |
| `exercise_id` | VARCHAR(50) | NOT NULL | Identificador del tipo de ejercicio (ej: "resonancia_01"). |
| `exercise_type` | VARCHAR(20) | NOT NULL | Categoría del ejercicio: "resonancia", "estabilidad", "rango_tono". |
| `avg_hz` | NUMERIC(8,2) | NOT NULL | Frecuencia promedio (Hz) capturada en este ejercicio. |
| `stability` | NUMERIC(5,2) | NOT NULL | Métrica de estabilidad vocal (0 a 100). |
| `breaks` | INTEGER | NOT NULL | Cantidad de quiebres vocales detectados. |
| `in_range` | BOOLEAN | NOT NULL | Indica si la voz estuvo dentro del rango esperado para el ejercicio. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Fecha y hora de creación del resultado. |

**Relación:** muchos `exercise_results` pertenecen a una `phonation_session`.

### Migración

La creación de estas tablas se define en la migración `0c400000111e_initial_schema.py`. Las restricciones de clave foránea con `ON DELETE CASCADE` garantizan que la eliminación de un usuario o sesión elimine automáticamente sus registros asociados.

## 4. Esquemas de solicitud y respuesta

Los esquemas definen los contratos entre el cliente y el servidor, incluida validación de tipos.

### `ExerciseResultRequest`

Representa un resultado individual de ejercicio que el frontend envía al backend.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `exercise_id` | str | Identificador del ejercicio. |
| `exercise_type` | str | Tipo: "resonancia", "estabilidad", "rango_tono". |
| `avg_hz` | float | Frecuencia promedio en Hz. |
| `stability` | float | Estabilidad (0-100). |
| `breaks` | int | Número de quiebres. |
| `in_range` | bool | Si la voz estuvo en el rango objetivo. |

### `PhonationSessionRequest`

Representa una sesión completa de fonación con todos sus ejercicios.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `overall_score` | float | Puntuación general (0-100). |
| `avg_hz` | float | Frecuencia promedio de la sesión. |
| `observations` | list[str] | Notas o comentarios. |
| `exercises` | list[ExerciseResultRequest] | Lista de ejercicios realizados. |

### `PhonationSessionResponse`

Respuesta serializada de una sesión completa con todos sus ejercicios. Incluye los mismos campos que el request más `id`, `created_at` y `exercises` como lista de `ExerciseResultResponse`.

### `PhonationSessionListItem`

Respuesta compacta para listar sesiones sin detalles de ejercicios.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | Identificador de la sesión. |
| `overall_score` | float | Puntuación general. |
| `avg_hz` | float | Frecuencia promedio. |
| `created_at` | datetime | Fecha de creación. |

## 5. Casos de uso

Los casos de uso orquestan la persistencia y consulta de datos. Se implementan en `backend/app/use_cases/phonation/sessions.py`.

### `save_phonation_session(data, user, session)`

Persiste una nueva sesión de fonación con todos sus ejercicios asociados.

**Flujo de ejecución:**
1. Crear una instancia de `PhonationSession` con los datos de `data` y asignar `user_id`.
2. Ejecutar `session.flush()` para generar el identificador UUID de la sesión sin hacer commit.
3. Ejecutar `session.refresh(phonation_session)` para sincronizar el objeto con la base de datos.
4. Iterar sobre cada ejercicio en `data.exercises` y crear instancias de `ExerciseResult` asociadas a la sesión.
5. Ejecutar `session.commit()` para persistir todas las operaciones.
6. Ejecutar `session.refresh(phonation_session)` para cargar los ejercicios asociados.
7. Retornar la instancia de `PhonationSession` completamente poblada.

### `list_phonation_sessions(user, session)`

Consulta todas las sesiones de fonación del usuario autenticado, ordenadas por `created_at` descendente.

### `get_phonation_session(session_id, user, session)`

Consulta una sesión específica y sus ejercicios. Usa `selectinload(exercise_results)` para carga eficiente. Valida que `user_id` de la sesión coincida con el del usuario autenticado.

**Errores posibles:**
- `NotFoundException` si la sesión no existe.
- `UnauthorizedException` si el usuario no es propietario.

## 7. Endpoints de la API

### POST `/phonation/sessions`

Crea una nueva sesión de fonación.

- **Método:** POST
- **Autenticación:** Bearer token requerido
- **Código de respuesta:** 201 Created
- **Body:** `PhonationSessionRequest`
- **Respuesta:** `PhonationSessionResponse`

**Errores:**
- `401 Unauthorized` — Token ausente o inválido.
- `422 Unprocessable Entity` — Validación fallida.

---

### GET `/phonation/sessions`

Lista todas las sesiones del usuario autenticado en orden descendente.

- **Método:** GET
- **Autenticación:** Bearer token requerido
- **Código de respuesta:** 200 OK
- **Respuesta:** `list[PhonationSessionListItem]`

**Nota:** Retorna lista vacía si el usuario no tiene sesiones registradas.

---

### GET `/phonation/sessions/{session_id}`

Retorna los detalles completos de una sesión específica con todos sus ejercicios.

- **Método:** GET
- **Autenticación:** Bearer token requerido
- **Código de respuesta:** 200 OK
- **Respuesta:** `PhonationSessionResponse`

**Errores:**
- `401 Unauthorized` — Token ausente o inválido.
- `404 Not Found` — La sesión no existe.
- `403 Forbidden` — La sesión existe pero pertenece a otro usuario.
