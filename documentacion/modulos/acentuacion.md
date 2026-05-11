# Acentuación — Documentación Backend

## 1. Descripción funcional

El módulo de Acentuación entrena al usuario a leer frases respetando el patrón acentual del español. El flujo:

1. El frontend muestra una frase y graba al usuario leyéndola en voz alta.
2. El frontend envía cada frase grabada al endpoint de evaluación, que llama a Gemini AI y retorna las puntuaciones (pronunciación, ritmo, entonación, acentuación) más feedback verbal específico.
3. El frontend agrega los resultados de todas las frases de la sesión y los envía al endpoint de creación de sesión.
4. El backend persiste solo las métricas agregadas; el feedback verbal se descarta tras mostrarlo en la UI.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/accentuation.py` | Endpoints HTTP (evaluate + sessions CRUD), mapeo de errores. |
| Schemas | `backend/app/presentation/schemas/accentuation.py` | Contratos Pydantic v2 (per-frase efímero + sesión persistida). |
| Use cases | `backend/app/use_cases/accentuation/evaluate_phrase.py`, `sessions.py` | Llamada a Gemini con corte temprano por silencio + persistencia de sesiones. |
| Infra AI | `backend/app/infrastructure/ai/gemini.py` | Cliente Gemini con prompt y schema de respuesta. |
| Infra audio | `backend/app/infrastructure/audio/silence_detector.py` | Detector de silencio para evitar llamadas Gemini sin habla. |
| Entidades | `backend/app/domain/entities/session.py`, `accentuation_metrics.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

Una sesión de acentuación se representa con dos filas: la raíz `sessions` y su 1:1 `accentuation_metrics`. **No hay tabla hija**: las evaluaciones por frase son efímeras (van al frontend desde Gemini, no al backend de persistencia).

### `sessions` (raíz, compartida)

Para acentuación standalone: `module='accentuation'`, `parent_id=NULL`, `status='completed'`. `score` lo deriva el backend.

### `accentuation_metrics` (1:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `pronunciation_score` | SMALLINT | NOT NULL, CHECK 0-100 | Puntuación agregada de pronunciación. |
| `rhythm_score` | SMALLINT | NOT NULL, CHECK 0-100 | Puntuación agregada de ritmo. |
| `intonation_score` | SMALLINT | NOT NULL, CHECK 0-100 | Puntuación agregada de entonación. |
| `stress_score` | SMALLINT | NOT NULL, CHECK 0-100 | Puntuación agregada de acentuación. |
| `phrases_count` | INT | NOT NULL DEFAULT 0 | Cantidad de frases evaluadas en la sesión. |

### Decisiones de diseño

- **Tabla hija `phrase_evaluations` eliminada**: las evaluaciones por frase incluían `phrase_text`, `feedback`, `specific_errors` — todo texto generado por LLM sin valor longitudinal. El JSON propuesta lo dropeó explícitamente. Si el feedback necesita mostrarse al usuario tras la sesión, se cachea fuera de BD (Redis con TTL, según la sección `ephemeral_storage` del propuesta).
- **`summary_feedback` eliminado**: mismo razonamiento; texto de LLM sin uso analítico.
- **`stress_accuracy_score` → `stress_score`**: alineado con la convención `_score` del nuevo schema. El cambio incluye la prompt de Gemini, su `response_schema`, y la respuesta de silencio en `evaluate_phrase`.
- **`score` derivado en backend = promedio redondeado de los 4 sub-scores**: fórmula canónica única (precedente loudness, no phonation). Si en el futuro se quiere ponderar (p.ej. dar más peso a `pronunciation_score`), cambia en `_derive_overall_score` en un solo lugar.
- **`phrases_count >= 1`**: una sesión sin frases no tiene sentido; validador en Pydantic.
- **El endpoint `/evaluate` se mantiene**: es la fuente de las puntuaciones por frase. Su respuesta carga `feedback` y `specific_errors` para mostrar en UI durante la sesión, pero ninguno de esos campos termina en BD.

## 4. Esquemas

### Evaluación por frase (efímera)

`PhraseSpecificError`: `word`, `expected_stress`, `actual_issue`, `suggestion`. (Texto generado por Gemini.)

`PhraseEvaluation`: `phrase_text`, `phrase_index`, `overall_score` (0-100, ephemeral, no persistido), `pronunciation_score`, `rhythm_score`, `intonation_score`, `stress_score` (todos 0-100), `feedback`, `specific_errors`.

### Métricas persistidas

`AccentuationMetricsInput`: 4 sub-scores (0-100) + `phrases_count` (>=1).

`AccentuationMetricsOutput`: mismos campos.

### Sesión

`AccentuationSessionCreate`: `started_at`, `ended_at`, `metrics`. **Sin `score`**: el backend lo deriva. Validador `validate_time_range` chequea `ended_at > started_at`.

`AccentuationSessionDetail`: `id`, `user_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`, `metrics`.

`AccentuationSessionListItem` (compacto): `id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `phrases_count`.

## 5. Casos de uso

### `evaluate_phrase(audio_bytes, mime_type, phrase_text)` — `evaluate_phrase.py`

1. Si el detector local de silencio marca el audio como vacío, retorna `_SILENCE_RESPONSE` (todos los scores en 0, feedback fijo). Evita el costo de una llamada Gemini sin habla.
2. Si el detector falla por error, se loggea warning y se procede a Gemini (que también tiene manejo de silencio en su prompt).
3. Llama a `GeminiAccentuationService.evaluate_phrase` y retorna el dict tal cual viene de Gemini.

### `create_accentuation_session(db, user, payload)` — `sessions.py`

En una transacción inserta `sessions(module='accentuation', status='completed', parent_id=NULL)` con `duration_ms` derivado y `score` calculado por `_derive_overall_score` + `accentuation_metrics` 1:1.

### `_derive_overall_score(payload)` — `sessions.py`

Promedio redondeado de los 4 sub-scores. Función separada para que el cambio de fórmula (si llega) sea local.

### `list_accentuation_sessions(db, user)`

JOIN `sessions + accentuation_metrics`, filtra `module='accentuation' AND parent_id IS NULL`, ordena por `started_at DESC`.

### `get_accentuation_session(db, user, session_id)`

Detalle. Retorna `None` para no-encontrado o cross-user (router → 404 sin distinguir).

## 6. Endpoints

- `POST /accentuation/evaluate` — multipart con `audio` (UploadFile), `phrase_text` (Form), `phrase_index` (Form). Retorna `PhraseEvaluation` (no persiste nada). 502 si Gemini falla.
- `POST /accentuation/sessions` → 201 / 422.
- `GET /accentuation/sessions` → 200, lista standalone ordenada por `started_at DESC`.
- `GET /accentuation/sessions/{id}` → 200 / 404.

Todos los endpoints requieren Bearer JWT.

## 7. Pendientes en el roadmap

- **Composición en sesión live**: cuando se reescriba `live`, `create_accentuation_session` debe aceptar `parent_id` opcional.
- **Sesiones abortadas**: hoy solo `status='completed'`.
- **Cache efímera de `feedback` Gemini**: el JSON propuesta sugiere Redis con TTL 7-30 días para mostrar el feedback al usuario después de la sesión. No implementado todavía; hoy el feedback solo vive en la respuesta inmediata del `/evaluate`.
