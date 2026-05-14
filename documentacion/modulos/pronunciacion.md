# Pronunciación — Documentación Backend

## 1. Descripción funcional

El módulo de Pronunciación entrena al usuario a articular fonemas del español con precisión. El flujo es estructuralmente igual al de acentuación:

1. El frontend muestra una frase y graba al usuario leyéndola.
2. Cada frase grabada se envía al endpoint de evaluación, que llama a Gemini AI y retorna 5 puntuaciones (vocálica, consonántica, fluidez, inteligibilidad, overall) más feedback verbal y errores fonémicos específicos.
3. El frontend agrega los resultados de todas las frases y los envía al endpoint de creación de sesión, indicando además el `level` de dificultad usado.
4. El backend persiste solo las métricas agregadas y el nivel; el feedback verbal y los errores fonémicos se descartan tras mostrarlos en la UI.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/pronunciation.py` | Endpoints HTTP (evaluate + sessions CRUD), mapeo de errores. |
| Schemas | `backend/app/presentation/schemas/pronunciation.py` | Contratos Pydantic v2 (per-frase efímero + sesión persistida). |
| Use cases | `backend/app/use_cases/pronunciation/evaluate_phrase.py`, `sessions.py` | Llamada a Gemini con corte temprano por silencio + persistencia de sesiones. |
| Infra AI | `backend/app/infrastructure/ai/pronunciation_gemini.py` | Cliente Gemini con prompt fonético-clínico y schema de respuesta. |
| Infra audio | `backend/app/infrastructure/audio/silence_detector.py` | Detector de silencio (compartido con acentuación). |
| Entidades | `backend/app/domain/entities/session.py`, `pronunciation_metrics.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

Una sesión de pronunciación se representa con dos filas: la raíz `sessions` y su 1:1 `pronunciation_metrics`. **No hay tabla hija**: las evaluaciones por frase son efímeras.

### `sessions` (raíz, compartida)

Para pronunciación standalone: `module='pronunciation'`, `parent_id=NULL`, `status='completed'`. `score` lo deriva el backend.

### `pronunciation_metrics` (1:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `level` | VARCHAR(20) | NOT NULL | Nivel de dificultad usado en la sesión (string libre). |
| `vowel_score` | SMALLINT | NOT NULL, CHECK 0-100 | Producción vocálica agregada. |
| `consonant_score` | SMALLINT | NOT NULL, CHECK 0-100 | Producción consonántica agregada. |
| `fluency_score` | SMALLINT | NOT NULL, CHECK 0-100 | Fluidez fonética agregada. |
| `intelligibility_score` | SMALLINT | NOT NULL, CHECK 0-100 | Inteligibilidad agregada. |
| `phrases_count` | INT | NOT NULL DEFAULT 0 | Cantidad de frases evaluadas. |

### Decisiones de diseño

- **Tabla hija `phrase_pronunciations` eliminada**: las evaluaciones por frase incluían `phrase_text`, `feedback`, `phoneme_errors` — todo texto generado por LLM sin valor longitudinal. El JSON propuesta lo dropeó explícitamente.
- **`summary_feedback` eliminado**: mismo razonamiento.
- **`score` derivado en backend = promedio redondeado de los 4 sub-scores** (vocálica, consonántica, fluidez, inteligibilidad). Sigue el precedente loudness/acentuación: cuando la fórmula del overall es canónica única, deriva en backend; si quieres ponderar (p.ej. dar más peso a inteligibilidad), cambia en `_derive_overall_score` en un solo lugar.
- **`level` como string libre 1-20 chars**: el JSON propuesta usa VARCHAR(20) sin enum porque los niveles cambian con el contenido del catálogo (frontend define qué ofrece). Si alguna vez se requiere un set fijo de niveles, conviene migrar a enum nativo en BD y `Literal` en Pydantic.
- **Schema Gemini con `"type": "integer"`** para los 5 score fields: garantiza que Gemini no devuelva floats que romperían la validación Pydantic int del lado del servidor. Lección importada del review post-commit de acentuación.
- **`phrases_count >= 1`**: una sesión sin frases no tiene sentido.
- **Sin whitelist explícita de MIME types**: igual que acentuación, se usa `audio.content_type or "audio/webm"` como default. Si el frontend manda algo raro Gemini se queja. Endurecer (mime allowlist + 415) queda como refactor unificado para ambos módulos.

## 4. Esquemas

### Evaluación por frase (efímera)

`PhonemeError`: `phoneme`, `word`, `actual_issue`, `suggestion`. (Texto generado por Gemini.)

`PhraseEvaluation`: `phrase_text`, `phrase_index`, `overall_score` (0-100, ephemeral), `vowel_score`, `consonant_score`, `fluency_score`, `intelligibility_score` (todos 0-100), `feedback`, `phoneme_errors`.

### Métricas persistidas

`PronunciationMetricsInput`: `level` (1-20 chars) + 4 sub-scores (0-100) + `phrases_count` (>=1).

`PronunciationMetricsOutput`: mismos campos.

### Sesión

`PronunciationSessionCreate`: `started_at`, `ended_at`, `metrics`. **Sin `score`**: el backend lo deriva. Validador `validate_time_range` chequea `ended_at > started_at`.

`PronunciationSessionDetail`: `id`, `user_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`, `metrics`.

`PronunciationSessionListItem` (compacto): `id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `level`, `phrases_count`. Incluye `level` para que la card de timeline muestre con qué nivel se entrenó.

## 5. Casos de uso

### `evaluate_phrase(audio_bytes, mime_type, phrase_text, level)` — `evaluate_phrase.py`

1. Si el detector local de silencio marca el audio como vacío, retorna `_SILENCE_RESPONSE` (todos los scores en 0). Evita la llamada a Gemini.
2. Si el detector falla, se loggea warning y se procede a Gemini.
3. Llama a `GeminiPronunciationService.evaluate_phrase` y retorna el dict de Gemini.

### `create_pronunciation_session(db, user, payload)` — `sessions.py`

En una transacción inserta `sessions(module='pronunciation', status='completed', parent_id=NULL)` con `duration_ms` y `score` derivados + `pronunciation_metrics` 1:1 (incluye `level`).

### `_derive_overall_score(payload)`

Promedio redondeado de los 4 sub-scores. Función separada por mantenibilidad.

### `list_pronunciation_sessions(db, user)`

JOIN, filtro `module='pronunciation' AND parent_id IS NULL`, orden por `started_at DESC`.

### `get_pronunciation_session(db, user, session_id)`

Detalle. Retorna `None` para no-encontrado o cross-user.

## 6. Endpoints

- `GET /pronunciation/phrases?level=...` → 200 `list[{id, text, difficulty}]`. Catálogo activo del módulo. `level` (opcional) filtra por `prompts.difficulty` (`basico` | `intermedio` | `avanzado`). Sin el query param, devuelve el catálogo completo. Reemplaza la lista hardcoded del frontend.
- `POST /pronunciation/evaluate` — multipart con `audio`, `phrase_text`, `phrase_index`, `level` (Form). Retorna `PhraseEvaluation`. 502 si Gemini falla.
- `POST /pronunciation/sessions` → 201 / 422.
- `GET /pronunciation/sessions` → 200, lista standalone ordenada por `started_at DESC`.
- `GET /pronunciation/sessions/{id}` → 200 / 404.

Todos requieren Bearer JWT.

### Catálogo `prompts` (módulo `pronunciation`)

Las 18 frases iniciales viven en la tabla `prompts` (seeded por `_seed_pronunciation_phrases`), seis por nivel (`basico`, `intermedio`, `avanzado` en `prompts.difficulty`). El use_case `list_phrases(db, difficulty?)` y el endpoint `GET /pronunciation/phrases` exponen el catálogo al frontend. El use_case `get_phrase_by_id(db, prompt_id)` valida que un id sea conocido, activo y del módulo correcto; se usará para el flujo de B7 (persistir `prompt_id` por frase evaluada).

## 7. Pendientes en el roadmap

- **Composición en sesión live**: cuando se reescriba `live`, `create_pronunciation_session` debe aceptar `parent_id` opcional.
- **Sesiones abortadas**: hoy solo `status='completed'`.
- **Cache efímera de feedback Gemini**: igual que acentuación, hoy el feedback solo vive en la respuesta inmediata del `/evaluate`. Si se quiere mostrar después de la sesión: Redis con TTL.
- **MIME allowlist unificada**: implementada en `app/infrastructure/audio/mime.py` (ver `documentacion/audio-mime-allowlist.md`). El endpoint `/evaluate` ya rechaza con 415 cualquier `Content-Type` fuera de la allowlist en lugar del fallback silencioso a `audio/webm`.
- **`level` como enum nativo**: si los niveles se vuelven catálogo cerrado, migrar a Postgres ENUM + `Literal` en Pydantic.
