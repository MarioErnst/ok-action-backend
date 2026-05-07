# Módulo: Expresión Facial (live emotion tracking)

## Qué hace

Persiste sesiones de análisis facial en vivo enviadas por el frontend. Una sesión es una secuencia de **eventos de cambio de emoción dominante** detectados en el cliente. El backend valida el payload, calcula la distribución temporal de emociones y persiste todo.

## Arquitectura

```
Frontend (MediaPipe FaceLandmarker + heurísticas FACS en navegador)
  ▼ Detección a 15fps. Solo se captura un evento cuando cambia
  ▼ la emoción dominante.
  ▼
POST /facial-expression/sessions
  ▼ { duration_ms, events: [{t_ms, emotion, gestures}] }
  ▼
SessionCreateRequest (validación Pydantic)
  ▼
save_facial_expression_session
  ▼ compute_distribution -> {emotion: pct, dominant, dominant_pct}
  ▼ INSERT facial_expression_sessions
  ▼ INSERT N facial_expression_emotion_events
  ▼
SessionDetailResponse
```

El frontend hace toda la detección y clasificación con heurísticas FACS. El backend NO calcula emociones, solo agrega y persiste.

## Endpoints

### POST `/facial-expression/sessions`

Persiste una sesión completa. Devuelve el detalle con distribución calculada.

**Request body** (`SessionCreateRequest`):

```json
{
  "duration_ms": 73000,
  "events": [
    {"t_ms": 0,     "emotion": "neutral", "gestures": {}},
    {"t_ms": 4200,  "emotion": "happy",   "gestures": {"mouthSmile": 0.78, "cheekSquint": 0.45}},
    {"t_ms": 31000, "emotion": "surprise","gestures": {"jawOpen": 0.62}}
  ]
}
```

**Response 201** (`SessionDetailResponse`):

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "duration_ms": 73000,
  "dominant_emotion": "happy",
  "dominant_percentage": 37,
  "emotion_distribution": {"neutral": 6, "happy": 37, "surprise": 57},
  "created_at": "2026-05-07T22:31:14+00:00",
  "events": [...]
}
```

### GET `/facial-expression/sessions`

Lista resumida del usuario autenticado, descendente por fecha.

### GET `/facial-expression/sessions/{session_id}`

Detalle completo. UUID malformado o sesión no propia → 404.

## Algoritmo: distribución temporal (`distribution.py`)

Cada evento marca el instante en que **comienza** una emoción. El tiempo en cada emoción es la diferencia con el siguiente evento (o con `duration_ms` para el último). Las repeticiones de la misma emoción acumulan.

Ejemplo:

```
duration = 10000ms
events = [{t:0, "happy"}, {t:4000, "neutral"}]
  -> happy: 0..4000  = 4000ms (40%)
  -> neutral: 4000..10000 = 6000ms (60%)
```

### Largest-remainder rounding

Para que las barras siempre sumen 100%, los porcentajes se calculan con **largest-remainder rounding**: floor de cada porcentaje y luego se reparte el residuo (100 - sum) sumando 1 a las emociones con mayor parte fraccional. Esto evita el bug de UX donde tres tercios renderean como 33+33+33=99%.

### Sin eventos o duración cero

`compute_distribution` devuelve `({}, None, None)` cuando no hay eventos o `duration_ms == 0`. Es un caso defensivo: el schema exige `duration_ms >= 0` y al menos un evento es esperable, pero el código no asume que las dos cosas se cumplen.

## Validación de payload

Schema Pydantic `SessionCreateRequest`. Cualquier violación → 422.

| Constante                    | Valor    | Razón                                              |
|------------------------------|----------|----------------------------------------------------|
| `MAX_EVENTS_PER_SESSION`     | 5 000    | Sesiones reales tienen <100 eventos; 5k es slack   |
| `MAX_DURATION_MS`            | 1 800 000| 30 minutos, suficiente para casos extremos         |
| `MAX_GESTURE_KEYS`           | 60       | 52 blendshapes ARKit + slack                       |
| `ALLOWED_EMOTIONS`           | set de 7 | Allow-list server-side: `happy`, `sad`, `angry`, `surprise`, `fear`, `disgust`, `neutral` |

| Campo                   | Restricción                  |
|-------------------------|------------------------------|
| `duration_ms`           | `0 <= n <= MAX_DURATION_MS`  |
| `events`                | `<= MAX_EVENTS_PER_SESSION`  |
| `events[].t_ms`         | `0 <= n <= MAX_DURATION_MS`  |
| `events[].emotion`      | `1..20` chars + en allow-list |
| `events[].gestures`     | objeto con `<= 60` claves    |

El router valida emociones contra `ALLOWED_EMOTIONS` antes de persistir y devuelve 422 con mensaje `"Emoción no soportada: <id>"` si encuentra una no permitida. Esto evita que typos del cliente corrompan la analítica silenciosamente.

## Manejo de errores

- `try/except` envuelve la llamada al caso de uso. Si falla, `await session.rollback()` antes de re-lanzar — la conexión vuelve al pool limpia.
- UUID malformado en GET → 404 (validado con `uuid.UUID(s)` antes de tocar la DB).
- Eventos con emoción fuera de la allow-list → 422.

## Tablas

### `facial_expression_sessions`

| Columna             | Tipo            | Descripción                                       |
|---------------------|-----------------|---------------------------------------------------|
| id                  | UUID PK         | Identificador de sesión                           |
| user_id             | UUID FK         | Owner; CASCADE on user delete                     |
| duration_ms         | INTEGER         | Duración total de la sesión                       |
| dominant_emotion    | VARCHAR(20) NULL| Emoción con mayor tiempo; NULL si sin eventos     |
| dominant_percentage | INTEGER NULL    | % de tiempo en la dominante; NULL si sin eventos  |
| emotion_distribution| JSONB           | Map `{emotion: percentage}` que suma 100          |
| created_at          | TIMESTAMPTZ     | Fecha de creación                                 |

### `facial_expression_emotion_events`

| Columna     | Tipo        | Descripción                                       |
|-------------|-------------|---------------------------------------------------|
| id          | UUID PK     | Identificador de evento                           |
| session_id  | UUID FK     | Sesión a la que pertenece; CASCADE                |
| t_ms        | INTEGER     | Timestamp dentro de la sesión                     |
| emotion     | VARCHAR(20) | Emoción dominante a partir de este instante       |
| gestures    | JSONB       | Snapshot de gestos activos `{gesture_id: 0..1}`   |

Índice `ix_facial_expression_emotion_events_session_id` para acelerar joins por sesión.

## Migración

`c1d2e3f4a5b6_replace_facial_question_results_with_emotion_events.py` reemplaza el modelo anterior basado en preguntas. Usa `DROP TABLE IF EXISTS` para que sea aplicable sobre cualquier estado intermedio (ej. una DB local que nunca había aplicado la migración previa).

## Decisiones de diseño

### Frontend detecta, backend solo agrega
Al mover la clasificación al cliente (con MediaPipe + heurísticas FACS) bajamos el costo de cómputo del servidor a casi cero y eliminamos la necesidad de procesar imágenes en el backend. El backend solo hace agregaciones temporales sobre eventos discretos.

### Allow-list de emociones server-side
El frontend podría tener bugs o un atacante podría POST-ear emociones inventadas. La allow-list garantiza que la columna `dominant_emotion` y las claves de `emotion_distribution` siempre sean valores conocidos para analytics.

### Largest-remainder en lugar de redondeo simple
Las barras de UI suman 100% siempre. Sin esto, un usuario ve "happy 33 + sad 33 + neutral 33 = 99" y duda de los datos.

### `dominant_*` nullable
Permite distinguir "sesión sin eventos" de "ningún emotion ganó (imposible)". El frontend renderiza un `—` cuando es NULL.
