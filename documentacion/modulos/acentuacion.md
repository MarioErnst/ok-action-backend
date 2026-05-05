# Acentuación — Documentación Backend

## 1. Descripción funcional

El módulo de Acentuación permite la evaluación asistida por inteligencia artificial del acento prosódico, ritmo, entonación y precisión del estrés silábico en frases grabadas por el usuario en español.

El flujo de uso es el siguiente:

1. El usuario graba una frase en voz alta a través de la interfaz de cliente.
2. El archivo de audio se envía al backend junto con el texto de la frase.
3. El servicio de IA (Gemini) analiza el audio contra patrones de pronunciación española.
4. Se detectan errores específicos por palabra con sugerencias de corrección.
5. El usuario puede evaluar múltiples frases en una sesión.
6. Al terminar la sesión, se persiste toda la información con las evaluaciones de cada frase.

El módulo proporciona retroalimentación detallada sobre:

- Acento prosódico: patrones llana, aguda y esdrújula.
- Precisión del estrés silábico: identificación correcta de la sílaba tónica.
- Ritmo: cadencia y distribución temporal de las sílabas.
- Entonación: patrones declarativos, interrogativos y exclamativos.
- Pronunciación general: claridad y articulación.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| **Presentación (Router)** | `backend/app/presentation/routers/accentuation.py` | Define los endpoints HTTP y valida las solicitudes. |
| **Esquemas** | `backend/app/presentation/schemas/accentuation.py` | Define los modelos de datos para solicitudes y respuestas. |
| **Casos de uso** | `backend/app/use_cases/accentuation/` | Lógica de negocio: evaluación de frases y persistencia de sesiones. |
| **Entidades** | `backend/app/domain/entities/` | Objetos de dominio: `AccentuationSession`, `PhraseEvaluation`. |
| **Servicios de IA** | `backend/app/infrastructure/ai/gemini.py` | `GeminiAccentuationService`: integración con Gemini. |

Cada capa depende solo de las capas inferiores. El flujo de datos es unidireccional: presentación → casos de uso → persistencia.

## 3. Modelo de datos

### Tabla: `accentuation_sessions`

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la sesión. |
| `user_id` | UUID | FK → users (CASCADE) | Usuario propietario de la sesión. |
| `overall_score` | NUMERIC(5,2) | NOT NULL | Puntuación general (0-100). |
| `pronunciation_score` | NUMERIC(5,2) | NOT NULL | Puntuación de pronunciación (0-100). |
| `rhythm_score` | NUMERIC(5,2) | NOT NULL | Puntuación de ritmo (0-100). |
| `intonation_score` | NUMERIC(5,2) | NOT NULL | Puntuación de entonación (0-100). |
| `stress_accuracy_score` | NUMERIC(5,2) | NOT NULL | Puntuación de precisión del estrés silábico (0-100). |
| `summary_feedback` | TEXT | NOT NULL | Retroalimentación general de la sesión. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Marca temporal de creación (UTC). |

**Relación:** Una sesión tiene muchas evaluaciones de frases (`phrase_evaluations`).

### Tabla: `phrase_evaluations`

| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `id` | UUID | PK | Identificador único de la evaluación. |
| `session_id` | UUID | FK → accentuation_sessions (CASCADE) | Sesión a la que pertenece. |
| `phrase_text` | VARCHAR(500) | NOT NULL | Texto de la frase evaluada. |
| `phrase_index` | INTEGER | NOT NULL | Índice secuencial de la frase en la sesión (0-based). |
| `overall_score` | NUMERIC(5,2) | NOT NULL | Puntuación general de la frase (0-100). |
| `pronunciation_score` | NUMERIC(5,2) | NOT NULL | Puntuación de pronunciación (0-100). |
| `rhythm_score` | NUMERIC(5,2) | NOT NULL | Puntuación de ritmo (0-100). |
| `intonation_score` | NUMERIC(5,2) | NOT NULL | Puntuación de entonación (0-100). |
| `stress_accuracy_score` | NUMERIC(5,2) | NOT NULL | Puntuación de precisión del estrés (0-100). |
| `feedback` | TEXT | NOT NULL | Retroalimentación constructiva para la frase. |
| `specific_errors` | JSONB | NOT NULL | Array de objetos con errores específicos por palabra. |
| `created_at` | TIMESTAMPTZ | NOT NULL | Marca temporal de creación (UTC). |

**Estructura del campo `specific_errors` (JSONB):**

```json
[
  {
    "word": "sílaba",
    "expected_stress": "esdrújula",
    "actual_issue": "estrés en primera sílaba",
    "suggestion": "La palabra requiere estrés en la antepenúltima sílaba: sí-la-ba"
  }
]
```

### Migración

Archivo: `backend/alembic/versions/ca42c89bd609_add_accentuation_tables.py`

## 4. Esquemas de solicitud y respuesta

### `SpecificErrorSchema`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `word` | str | Palabra con el error detectado. |
| `expected_stress` | str | Tipo de acento esperado (ej: "esdrújula", "aguda"). |
| `actual_issue` | str | Descripción del problema observado. |
| `suggestion` | str | Recomendación para corregir. |

### `PhraseEvaluationResponse`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `phrase_text` | str | Texto de la frase evaluada. |
| `phrase_index` | int | Índice secuencial. |
| `overall_score` | float | Puntuación general (0-100). |
| `pronunciation_score` | float | Puntuación de pronunciación. |
| `rhythm_score` | float | Puntuación de ritmo. |
| `intonation_score` | float | Puntuación de entonación. |
| `stress_accuracy_score` | float | Puntuación de precisión del estrés. |
| `feedback` | str | Retroalimentación constructiva. |
| `specific_errors` | list[SpecificErrorSchema] | Errores por palabra. |

### `AccentuationSessionRequest`

Incluye los 5 scores consolidados de la sesión, `summary_feedback` y la lista de evaluaciones de frases.

### `AccentuationSessionResponse`

Igual al request más `id`, `user_id` y `created_at`.

### `AccentuationSessionListItem`

Respuesta compacta para listados: `id`, `overall_score`, `created_at`.

## 5. Casos de uso

### `evaluate_phrase(audio_bytes, mime_type, phrase_text)`

**Flujo:**
1. Detecta silencio. Si el audio es silencioso, retorna `_SILENCE_RESPONSE` (todos los scores en 0).
2. Si hay contenido, invoca `GeminiAccentuationService.evaluate_phrase()`.
3. Valida que los scores estén en el rango [0, 100].
4. Retorna `PhraseEvaluationResponse`.

**Errores:** `GeminiEvaluationError` si el servicio de IA falla.

### `save_accentuation_session(data, user, session)`

Crea `AccentuationSession` y, dentro de la misma transacción, una `PhraseEvaluation` por cada evaluación. Hace commit al finalizar.

### `list_accentuation_sessions(user, session)`

Consulta todas las sesiones del usuario ordenadas por `created_at` descendente.

### `get_accentuation_session(session_id, user, session)`

Carga la sesión con `selectinload(phrase_evaluations)`. Verifica que la sesión pertenezca al usuario.

**Errores:** `NotFoundError` si la sesión no existe. `UnauthorizedError` si el usuario no es propietario.

## 6. Integración con Gemini AI

### `GeminiAccentuationService`

**Ubicación:** `backend/app/infrastructure/ai/gemini.py`

**Modelo:** `gemini-2.5-flash`

**Entrada:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `audio_bytes` | bytes | Contenido binario del archivo de audio. |
| `mime_type` | str | Tipo MIME del audio. |
| `phrase_text` | str | Texto de la frase que se evaluará. |

**Prompt:** Evalúa desde la perspectiva de un profesor de español nativo. Analiza: acento prosódico (patrones llana/aguda/esdrújula), precisión del estrés silábico por palabra, entonación (declarativa/interrogativa/exclamativa), ritmo y articulación general.

**Salida JSON:**

```json
{
  "overall_score": 78,
  "pronunciation_score": 82,
  "rhythm_score": 75,
  "intonation_score": 80,
  "stress_accuracy_score": 72,
  "feedback": "Retroalimentacion constructiva en español.",
  "specific_errors": [
    {
      "word": "silaba",
      "expected_stress": "esdrujula",
      "actual_issue": "estres en primera silaba",
      "suggestion": "La palabra requiere estres en la antepenultima silaba"
    }
  ]
}
```

**Errores:** `GeminiEvaluationError` cuando la respuesta no puede parsearse. Se registra el error con contexto suficiente para diagnóstico.

**Credenciales:** La clave API de Gemini se lee desde `GEMINI_API_KEY` vía el módulo de configuración centralizado.

## 7. Endpoints de la API

### POST `/accentuation/evaluate`

Evalúa una frase grabada por el usuario.

- **Método:** POST — **Content-Type:** multipart/form-data
- **Autenticación:** Bearer token requerido

**Parámetros:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `audio` | file | Sí | Archivo de audio. |
| `phrase_text` | string | Sí | Texto de la frase evaluada. |
| `phrase_index` | integer | Sí | Índice secuencial (0-based). |

**Respuesta (200 OK):** `PhraseEvaluationResponse`

**Errores:** `400` — audio vacío o parámetros faltantes. `401` — token inválido.

---

### POST `/accentuation/sessions`

Crea una nueva sesión de acentuación con todas sus evaluaciones.

- **Método:** POST — **Código:** 201 Created
- **Body:** `AccentuationSessionRequest`
- **Respuesta:** `AccentuationSessionResponse`

---

### GET `/accentuation/sessions`

Lista todas las sesiones del usuario autenticado en orden descendente.

- **Respuesta (200 OK):** `list[AccentuationSessionListItem]`

---

### GET `/accentuation/sessions/{session_id}`

Detalles completos de una sesión con todas sus evaluaciones de frases.

- **Respuesta (200 OK):** `AccentuationSessionResponse`
- **Errores:** `404` — sesión no existe. `403` — sesión pertenece a otro usuario.
