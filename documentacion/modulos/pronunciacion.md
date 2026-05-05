# Pronunciación — Documentación Backend

## 1. Descripción funcional

El módulo de Pronunciación permite a los usuarios evaluar y mejorar su pronunciación del español a través de grabaciones de audio. El flujo funcional es el siguiente:

1. El usuario selecciona un nivel de dificultad: básico, intermedio o avanzado.
2. Graba una serie de frases en voz alta, una por una.
3. Cada grabación se envía al backend donde Gemini AI evalúa la pronunciación de forma fonética.
4. Se registran métricas detalladas para cada frase: puntuaciones de vocales, consonantes, fluidez e inteligibilidad.
5. Al finalizar todas las frases, se guarda la sesión completa con métricas consolidadas.
6. El usuario puede consultar el historial de sesiones y revisar el feedback detallado de cada evaluación.

## 2. Capas del módulo

El módulo está organizado en capas según el patrón de arquitectura limpia:

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| **Presentación** | `backend/app/presentation/routers/pronunciation.py` | Endpoints HTTP, gestión de rutas, validación de entrada. |
| **Schemas** | `backend/app/presentation/schemas/pronunciation.py` | Modelos de datos para solicitud y respuesta (Pydantic). |
| **Casos de uso** | `backend/app/use_cases/pronunciation/` | Lógica de negocio: evaluación de frases, guardado y consulta de sesiones. |
| **Entidades** | `backend/app/domain/entities/` | Objetos de dominio: `PronunciationSession`, `PhrasePronunciation`. |
| **Infraestructura (IA)** | `backend/app/infrastructure/ai/pronunciation_gemini.py` | Servicio `GeminiPronunciationService` que se comunica con Gemini AI. |

Cada capa tiene una única responsabilidad y comunica con la siguiente mediante contratos bien definidos.

## 3. Modelo de datos

### Tabla: `pronunciation_sessions`

Almacena información agregada de cada sesión de evaluación de pronunciación.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la sesión. |
| `user_id` | UUID | FK → users (CASCADE) | Usuario propietario de la sesión. |
| `level` | VARCHAR(20) | NOT NULL | Nivel de dificultad: 'basico', 'intermedio', 'avanzado'. |
| `overall_score` | NUMERIC(5,2) | NOT NULL | Puntuación global consolidada (0-100). |
| `vowel_score` | NUMERIC(5,2) | NOT NULL | Puntuación promedio de vocales (0-100). |
| `consonant_score` | NUMERIC(5,2) | NOT NULL | Puntuación promedio de consonantes (0-100). |
| `fluency_score` | NUMERIC(5,2) | NOT NULL | Puntuación promedio de fluidez (0-100). |
| `intelligibility_score` | NUMERIC(5,2) | NOT NULL | Puntuación promedio de inteligibilidad (0-100). |
| `summary_feedback` | TEXT | nullable | Retroalimentación general de la sesión. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Fecha y hora de creación. |

**Relación**: Una sesión tiene muchas `phrase_pronunciations` (relación 1:N).

### Tabla: `phrase_pronunciations`

Almacena evaluaciones detalladas de cada frase dentro de una sesión.

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la evaluación. |
| `session_id` | UUID | FK → pronunciation_sessions (CASCADE) | Sesión a la que pertenece. |
| `phrase_text` | VARCHAR(500) | NOT NULL | Texto de la frase evaluada. |
| `phrase_index` | INTEGER | NOT NULL | Índice ordinal de la frase en la sesión (0-based). |
| `overall_score` | NUMERIC(5,2) | NOT NULL | Puntuación global de la frase (0-100). |
| `vowel_score` | NUMERIC(5,2) | NOT NULL | Puntuación de vocales (0-100). |
| `consonant_score` | NUMERIC(5,2) | NOT NULL | Puntuación de consonantes (0-100). |
| `fluency_score` | NUMERIC(5,2) | NOT NULL | Puntuación de fluidez (0-100). |
| `intelligibility_score` | NUMERIC(5,2) | NOT NULL | Puntuación de inteligibilidad (0-100). |
| `feedback` | TEXT | nullable | Retroalimentación detallada de la frase. |
| `phoneme_errors` | JSONB | nullable | Array de objetos con errores de fonemas detectados. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Fecha y hora de evaluación. |

### Migración

Archivo: `backend/alembic/versions/428244644432_add_pronunciation_tables.py`

Crea ambas tablas con restricciones de integridad referencial. La clave foránea usa `ON DELETE CASCADE` para garantizar que al eliminar una sesión se eliminen sus frases asociadas.

## 4. Esquemas de solicitud y respuesta

### `PhonemeErrorSchema`

Representa un error detectado en la pronunciación de un fonema específico.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `phoneme` | str | Símbolo del fonema (ej. /r/, /ll/, /x/). |
| `word` | str | Palabra en la que se detectó el error. |
| `actual_issue` | str | Descripción del problema observado. |
| `suggestion` | str | Recomendación para mejorar. |

### `PhrasePronunciationResponse`

Respuesta de evaluación de una frase individual.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `phrase_text` | str | Texto de la frase evaluada. |
| `phrase_index` | int | Índice ordinal en la sesión. |
| `overall_score` | float | Puntuación global (0-100). |
| `vowel_score` | float | Puntuación de vocales (0-100). |
| `consonant_score` | float | Puntuación de consonantes (0-100). |
| `fluency_score` | float | Puntuación de fluidez (0-100). |
| `intelligibility_score` | float | Puntuación de inteligibilidad (0-100). |
| `feedback` | str | Retroalimentación constructiva. |
| `phoneme_errors` | list[PhonemeErrorSchema] | Lista de errores de fonemas detectados. |

### `PronunciationSessionRequest`

Solicitud para guardar una sesión completa. Incluye los 5 scores consolidados, `level`, `summary_feedback` y la lista de evaluaciones de frases.

### `PronunciationSessionResponse`

Igual al request más `id` y `created_at`.

### `PronunciationSessionListItem`

Respuesta compacta para listados: `id`, `level`, `overall_score`, `created_at`.

## 5. Casos de uso

### `evaluate_phrase(audio_bytes, mime_type, phrase_text, level)`

Evalúa fonéticamente una frase individual a partir de un archivo de audio.

**Flujo:**
1. Invoca el detector de silencio (`silence_detector`).
2. Si se detecta silencio puro, retorna `_SILENCE_RESPONSE`: todos los scores en 0 y feedback indicando audio vacío.
3. Si hay contenido de audio, invoca `GeminiPronunciationService.evaluate_phrase()`.
4. Retorna el resultado parseado como `PhrasePronunciationResponse`.

**Errores:** `GeminiPronunciationError` si Gemini no puede procesar el audio o la respuesta es inválida.

### `save_pronunciation_session(data, user, session)`

Persiste una sesión completa con todas sus evaluaciones.

**Flujo:**
1. Crea `PronunciationSession` con los datos agregados.
2. Por cada evaluación en `data.evaluations`, crea una `PhrasePronunciation`. Los `phoneme_errors` se almacenan como JSONB.
3. Hace commit de todas las operaciones en una transacción.

### `list_pronunciation_sessions(user, session)`

Consulta las sesiones del usuario ordenadas por `created_at` descendente.

### `get_pronunciation_session(session_id, user, session)`

Carga la sesión con `selectinload(phrase_pronunciations)`. Valida que `user_id` coincida con el usuario autenticado.

## 6. Integración con Gemini AI

### `GeminiPronunciationService`

**Ubicación:** `backend/app/infrastructure/ai/pronunciation_gemini.py`

**Modelo:** `gemini-2.5-flash`

**Entrada:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `audio_bytes` | bytes | Contenido binario del archivo de audio. |
| `mime_type` | str | Tipo MIME: webm, mp4, ogg, wav, mpeg. |
| `phrase_text` | str | Texto de la frase a evaluar. |
| `level` | str | Nivel del usuario: basico, intermedio, avanzado. |

**Prompt:** Actúa como experto en fonética clínica del español. Evalúa la producción de vocales (/a/, /e/, /i/, /o/, /u/) y consonantes (/r/, /rr/, /b/-/v/, /s/, /ll/-/y/, /x/, /d/), punto y modo de articulación, fluidez fonética e inteligibilidad.

**Salida JSON:**

```json
{
  "overall_score": 85,
  "vowel_score": 88,
  "consonant_score": 82,
  "fluency_score": 85,
  "intelligibility_score": 87,
  "feedback": "Texto constructivo de al menos 2 oraciones.",
  "phoneme_errors": [
    {
      "phoneme": "/r/",
      "word": "mejor",
      "actual_issue": "Descripcion del problema.",
      "suggestion": "Sugerencia de mejora."
    }
  ]
}
```

**Errores:** `GeminiPronunciationError` cuando la respuesta no puede parsearse.

## 7. Endpoints de la API

### POST `/pronunciation/evaluate`

Evalúa una frase individual en tiempo real.

- **Método:** POST
- **Content-Type:** multipart/form-data
- **Autenticación:** Bearer token requerido

**Parámetros:**

| Parámetro | Tipo | Ubicación | Descripción |
|-----------|------|-----------|-------------|
| `audio` | file | form | Archivo de audio (webm, mp4, ogg, wav, mpeg). |
| `phrase_text` | string | form | Texto de la frase evaluada. |
| `phrase_index` | integer | form | Índice ordinal (0-based). |
| `level` | string | form | Nivel: basico, intermedio, avanzado. |

**Respuesta (200 OK):** `PhrasePronunciationResponse`

**Errores:** `400` — audio vacío o formato inválido. `401` — token inválido.

---

### POST `/pronunciation/sessions`

Guarda una sesión completa de pronunciación.

- **Método:** POST — **Código:** 201 Created
- **Body:** `PronunciationSessionRequest`
- **Respuesta:** `PronunciationSessionResponse`

---

### GET `/pronunciation/sessions`

Lista las sesiones del usuario autenticado, ordenadas descendentemente.

- **Respuesta (200 OK):** `list[PronunciationSessionListItem]`

---

### GET `/pronunciation/sessions/{session_id}`

Detalles completos de una sesión con todas sus evaluaciones de frases.

- **Respuesta (200 OK):** `PronunciationSessionResponse`
- **Errores:** `404` — sesión no existe. `403` — sesión pertenece a otro usuario.
