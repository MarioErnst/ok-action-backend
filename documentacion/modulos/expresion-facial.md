# Módulo: Expresión Facial

## Qué hace

El módulo de expresión facial analiza el lenguaje no verbal del usuario durante una sesión de entrenamiento. El frontend captura frames de blendshapes faciales en tiempo real usando MediaPipe, y el backend recibe los datos crudos, calcula los puntajes por expresión y por pregunta, y persiste el resultado en la base de datos.

El módulo evalúa tres expresiones faciales relacionadas con nerviosismo o desconfianza:

- **Pucker** (fruncir los labios): capturado por el blendshape `mouthPucker`.
- **Brow Down** (bajar las cejas): promedio de `browDownLeft` y `browDownRight`.
- **Lips Down** (comisuras de los labios hacia abajo): promedio de `mouthFrownLeft` y `mouthFrownRight`.

---

## Arquitectura

```
Frontend (MediaPipe FaceLandmarker)
  → captura frames a 15fps
  → aplica calibración baseline por pregunta
  → acumula frames crudos por pregunta

POST /facial-expression/sessions
  → AnalyzeFacialExpressionSessionUseCase
  → calcula puntajes por expresión y por pregunta
  → persiste FacialExpressionSession + FacialExpressionQuestionResult[]
  → devuelve FacialExpressionSessionResponse
```

El frontend envía datos crudos (frames sin puntaje). El backend es el único responsable de calcular los puntajes. Esta separación garantiza consistencia y permite ajustar el algoritmo de scoring sin modificar el frontend.

---

## Algoritmo de scoring

### Umbrales (THRESHOLDS)

| Expresión  | Umbral |
|------------|--------|
| pucker     | 0.15   |
| brow_down  | 0.12   |
| lips_down  | 0.12   |

Un frame se considera positivo para una expresión cuando su valor supera el umbral correspondiente, descontando el valor baseline del usuario.

### Pesos (WEIGHTS)

| Expresión  | Peso |
|------------|------|
| pucker     | 0.40 |
| brow_down  | 0.35 |
| lips_down  | 0.25 |

### Cálculo por pregunta

1. Para cada frame, se resta el valor baseline del usuario a cada blendshape.
2. Se cuenta la proporción de frames donde el valor desviado supera el umbral.
3. Esa proporción (0.0 a 1.0) se convierte en puntaje 0–100 por expresión: `score = round((1 - proporcion) * 100)`.
4. El puntaje compuesto de la pregunta es la suma ponderada de los tres puntajes de expresión.

### Puntaje global

El `overall_score` de la sesión es el promedio simple de los `question_score` de todas las preguntas. Si la sesión no tiene preguntas (caso defensivo, no alcanzable vía API porque el schema exige `min_length=1`), `overall_score` es `None`. Esto distingue "sin datos" de "puntaje cero".

### Aserción de pesos

`WEIGHTS` debe sumar exactamente 1.0. Hay un `assert` al importar `analyze_session.py` que falla en arranque si alguien modifica los pesos sin balancearlos. Esto previene que un cambio accidental rompa la garantía de que el `question_score` está en el rango 0–100.

---

## Decisiones de diseño

### MediaPipe FaceLandmarker lite en el frontend

Se usa la variante lite del modelo para reducir el tamaño de descarga y el consumo de CPU/GPU en dispositivos móviles. El modelo se carga de forma lazy, solo cuando el usuario activa la pantalla de expresión facial. Mientras descarga, se muestra un estado de carga explícito al usuario.

### Calibración baseline al inicio de la sesión

Antes de responder las preguntas, el usuario realiza una calibración de 5 segundos (75 frames a 15fps) con la cara en reposo. Los valores promedio de esa calibración se almacenan como baseline. El scoring usa la desviación respecto al baseline, no valores absolutos. Esto corrige diferencias anatómicas entre usuarios (por ejemplo, personas con las cejas naturalmente bajas).

### Cap de 15fps en el loop de inferencia

El loop de detección facial está limitado a 15 frames por segundo mediante `requestAnimationFrame` con control de tiempo entre ejecuciones. Esto evita el sobrecalentamiento en hardware móvil y reduce el consumo de batería, sin impacto significativo en la calidad del análisis.

### Web Audio API para detección de voz (VAD)

La detección de actividad de voz (VAD) usa la Web Audio API (`AudioContext`, `AnalyserNode`). Se descartó el uso de `SpeechRecognition` (Web Speech API) porque no funciona en iOS Safari, que es uno de los targets del producto. La Web Audio API está disponible en todos los targets: iOS Safari, Chrome, Firefox y Android.

### El frontend envía datos crudos; el backend calcula los puntajes

El frontend no realiza ningún cálculo de scoring. Solo captura frames y los envía al backend. Esta decisión permite modificar umbrales, pesos o el algoritmo completo sin necesidad de actualizar el cliente. También simplifica los tests: la lógica de scoring está centralizada en el caso de uso del backend y se puede testear de forma unitaria.

---

## Validación de payload

El schema Pydantic `FacialExpressionSessionRequest` aplica las siguientes restricciones a nivel de API. Cualquier violación devuelve HTTP 422 antes de llegar al caso de uso.

### Constantes de límite

| Constante                     | Valor   | Razón                                                       |
|-------------------------------|---------|-------------------------------------------------------------|
| `MAX_FRAMES_PER_QUESTION`     | 18 000  | ~20 minutos a 15fps; muy por encima del uso normal          |
| `MAX_QUESTIONS_PER_SESSION`   | 50      | Evita payloads desproporcionados                            |
| `MAX_QUESTION_TEXT_LEN`       | 1 000   | Limita tamaño del texto de pregunta                         |
| `MAX_DURATION_MS`             | 600 000 | 10 minutos máximo por pregunta                              |

### Constraints por campo

| Campo                                | Restricción                  |
|--------------------------------------|------------------------------|
| `baseline.{pucker,brow_down,lips_down}` | `0.0 <= valor <= 1.0`     |
| `frames[].t`                         | `>= 0`                       |
| `frames[].{pk,bd,ld}`                | `0.0 <= valor <= 1.0`        |
| `question_id`                        | `1..50` caracteres           |
| `question_text`                      | `1..MAX_QUESTION_TEXT_LEN`   |
| `duration_ms`                        | `0..MAX_DURATION_MS`         |
| `frames`                             | `<= MAX_FRAMES_PER_QUESTION` |
| `questions`                          | `1..MAX_QUESTIONS_PER_SESSION` |

Estas validaciones cortan dos clases de problemas: datos corruptos de MediaPipe (valores fuera de `[0,1]`) y vectores de DOS por payload gigante.

---

## Manejo de errores y robustez

### Validación de UUID en GET

`GET /facial-expression/sessions/{session_id}` valida el formato UUID con `uuid.UUID(session_id)` antes de tocar la base de datos. Si el string no es un UUID válido, devuelve 404 directamente. Sin esta validación, el driver de Postgres lanza un `ValueError` que bubblea como 500.

### Rollback en POST

`create_session` envuelve la llamada al caso de uso en `try/except`. Si `save_facial_expression_session` falla (por cualquier motivo), el router llama `await session.rollback()` antes de re-lanzar la excepción. Esto garantiza que la conexión async vuelva al pool en estado limpio, sin dejar inserciones a medias visibles a otras transacciones.

### Scores nullable en respuesta

Los campos de score (`overall_score`, `pucker_score`, `brow_down_score`, `lips_down_score`, `question_score`) están tipados como `int | None` en los schemas de respuesta. Esto permite distinguir "scoring no se ejecutó" de "el usuario obtuvo cero". El router ya no transforma `None` en `0` con `or 0`.

---

## API endpoints

### POST `/facial-expression/sessions`

Recibe el baseline del usuario y los frames crudos por pregunta. Calcula y persiste los puntajes. Devuelve la sesión completa con resultados por pregunta.

**Request:** `FacialExpressionSessionRequest`
**Response:** `FacialExpressionSessionResponse`

### GET `/facial-expression/sessions`

Devuelve la lista de sesiones del usuario autenticado, ordenadas por fecha de creación descendente.

**Response:** `list[FacialExpressionSessionListItem]`

### GET `/facial-expression/sessions/{session_id}`

Devuelve el detalle de una sesión específica, incluyendo los resultados por pregunta.

**Response:** `FacialExpressionSessionResponse`

---

## Tablas de base de datos

### `facial_expression_sessions`

| Columna        | Tipo      | Descripción                              |
|----------------|-----------|------------------------------------------|
| id             | UUID PK   | Identificador único de la sesión         |
| user_id        | UUID FK   | Usuario propietario de la sesión         |
| overall_score  | INTEGER NULL | Puntaje global; NULL si la sesión no tiene preguntas |
| created_at     | TIMESTAMP | Fecha y hora de creación                 |

### `facial_expression_question_results`

| Columna         | Tipo      | Descripción                                          |
|-----------------|-----------|------------------------------------------------------|
| id              | UUID PK   | Identificador único del resultado                    |
| session_id      | UUID FK   | Sesión a la que pertenece este resultado             |
| question_id     | TEXT      | Identificador de la pregunta                         |
| question_text   | TEXT      | Texto de la pregunta respondida                      |
| duration_ms     | INTEGER   | Duración de la respuesta en milisegundos             |
| pucker_score    | INTEGER   | Puntaje 0–100 para la expresión pucker               |
| brow_down_score | INTEGER   | Puntaje 0–100 para la expresión brow down            |
| lips_down_score | INTEGER   | Puntaje 0–100 para la expresión lips down            |
| question_score  | INTEGER   | Puntaje compuesto 0–100 para la pregunta             |
