# Módulo: Versatilidad Lingüística

## Qué hace

Evalúa la **versatilidad lingüística** del usuario: qué tan variado es su vocabulario, si repite palabras de contenido o usa sinónimos, y la riqueza general de su léxico. La evaluación es íntegramente client-server: el cliente graba audio y lo sube al backend, el backend lo despacha a Gemini con un prompt afinado, y persiste solo las **métricas de desempeño** (no la transcripción ni el audio).

Dos modos de uso:

- **Guiado**: 3 preguntas predefinidas. El usuario responde una por una; cada respuesta se evalúa por separado y al final se promedian los puntajes.
- **Libre**: el usuario habla de lo que quiera durante el tiempo que necesite; al detener, se manda un único audio y se obtiene una sola evaluación.

## Modelo y stack

- **Gemini 2.5 Flash** (`gemini-2.5-flash`) vía `google-genai==1.16.0`.
- Audio multimodal directo: el cliente sube `audio/webm` (Chrome/Firefox) o `audio/mp4` (iOS Safari) y Gemini lo decodifica nativamente — no hay paso de transcripción intermedio.
- **Structured output** vía `response_schema`: Gemini siempre devuelve JSON con la forma exacta que esperamos.
- Modelo de datos en PostgreSQL, mismo patrón que el módulo `precision`.

## Arquitectura

```
Frontend (MediaRecorder + RecordButton)
  ▼ blob de audio (~250KB para 30s en mp4)
  ▼
POST /linguistic-versatility/sessions/{id}/rounds   (multipart)
  ▼ valida UUID, tamaño <= 5MB, mime allow-list
  ▼
evaluate_versatility_response (use case)
  ▼
GeminiVersatilityService.evaluate_response(audio, mime, question_text)
  ▼ Gemini retorna {versatility_score, vocabulary_richness, feedback, audio_intelligible}
  ▼
INSERT linguistic_versatility_rounds + UPDATE completed_rounds
  ▼
EvaluateRoundResponse → frontend
```

## Endpoints

### Modo guiado

| Método | Path                                                   | Qué hace                                                 |
|--------|--------------------------------------------------------|----------------------------------------------------------|
| POST   | `/linguistic-versatility/sessions`                     | Abre sesión, selecciona 3 preguntas evitando recientes   |
| POST   | `/linguistic-versatility/sessions/{id}/rounds`         | Sube audio de una respuesta y devuelve su evaluación     |
| POST   | `/linguistic-versatility/sessions/{id}/finalize`       | Cierra la sesión y calcula `overall_score` (promedio)    |
| PATCH  | `/linguistic-versatility/sessions/{id}/abandon`        | Marca la sesión como abandonada (idempotente)            |
| GET    | `/linguistic-versatility/sessions/{id}`                | Detalle completo con todos los rounds                    |
| GET    | `/linguistic-versatility/history`                      | Lista de sesiones del usuario, descendente por fecha     |

### Modo libre

| Método | Path                              | Qué hace                                              |
|--------|-----------------------------------|-------------------------------------------------------|
| POST   | `/linguistic-versatility/free`    | Recibe audio único, crea + finaliza sesión + round    |

Todos requieren `Authorization: Bearer <token>`.

## Validación de payload

Schema Pydantic + chequeo en router:

| Campo                | Restricción                                          |
|----------------------|------------------------------------------------------|
| `audio` (upload)     | <= 5 MB; HTTP 413 si lo excede                       |
| `audio.content_type` | Allow-list: `webm`, `mp4`, `ogg`, `wav`, `mpeg` (otros caen a `audio/webm`) |
| `question_id`        | UUID válido + existe en DB; HTTP 404 si no            |
| `versatility_score`  | int 0..100 en respuesta                              |
| `vocabulary_richness`| int 1..3 (1=básico, 2=intermedio, 3=avanzado)        |

## Prompt de Gemini

Dos plantillas en `infrastructure/ai/linguistic_versatility_gemini.py`:

- `_GUIDED_PROMPT_TEMPLATE`: incluye la pregunta. Define `versatility_score` (variedad léxica 0-100), `vocabulary_richness` (1-3), `feedback` (1-2 oraciones específicas, en rioplatense, citando palabra repetida + sinónimo), y `audio_intelligible` (false en caso de silencio/ruido).
- `_FREE_PROMPT_TEMPLATE`: igual estructura pero para discurso libre sin pregunta.

Ambas instruyen explícitamente:

- Ignorar repeticiones de palabras de función (artículos, pronombres, conectores).
- Penalizar solo repeticiones de palabras de contenido cuando hay sinónimos claros.
- No penalizar por ruido de fondo o calidad de audio.
- Devolver el feedback en español rioplatense (vos, no tú).
- En caso de audio ininteligible, scores neutrales y mensaje fijo "No se pudo procesar el audio".

## Tablas

### `linguistic_versatility_questions`

| Columna           | Tipo        | Descripción                                |
|-------------------|-------------|--------------------------------------------|
| id                | UUID PK     |                                            |
| text              | TEXT        | Texto de la pregunta                       |
| category          | VARCHAR(100)| `personal_experience`, `persuasion`, etc.  |
| difficulty_level  | VARCHAR(20) | `basic`, `intermediate`, `advanced`        |
| is_active         | BOOLEAN     | `false` para deprecar sin perder histórico |
| created_at        | TIMESTAMPTZ |                                            |

Seed: 3 preguntas iniciales en la migración (categorías `personal_experience`, `persuasion`, `speculative`).

### `linguistic_versatility_sessions`

| Columna           | Tipo        | Descripción                                          |
|-------------------|-------------|------------------------------------------------------|
| id                | UUID PK     |                                                      |
| user_id           | UUID FK     | CASCADE on user delete                               |
| mode              | VARCHAR(20) | `guided` o `free`                                    |
| total_rounds      | INTEGER     | 3 para guided, 1 para free                           |
| completed_rounds  | INTEGER     | Rounds con audio inteligible                         |
| overall_score     | INTEGER NULL| Promedio de versatility_score; NULL si sin rounds OK |
| status            | VARCHAR(20) | `active`, `completed`, `abandoned`                   |
| created_at        | TIMESTAMPTZ |                                                      |
| completed_at      | TIMESTAMPTZ NULL | Set en finalize/abandon                         |

### `linguistic_versatility_rounds`

| Columna             | Tipo         | Descripción                                       |
|---------------------|--------------|---------------------------------------------------|
| id                  | UUID PK      |                                                   |
| session_id          | UUID FK      | CASCADE                                           |
| question_id         | UUID FK NULL | NULL en modo free                                 |
| question_text       | TEXT NULL    | Snapshot del texto de la pregunta                 |
| versatility_score   | INTEGER NULL | 0..100; NULL si audio no inteligible              |
| vocabulary_richness | INTEGER NULL | 1..3; NULL si audio no inteligible                |
| feedback            | TEXT NULL    | Texto devuelto por Gemini                         |
| audio_intelligible  | BOOLEAN      | `false` cuando Gemini no pudo procesar            |
| created_at          | TIMESTAMPTZ  |                                                   |

Índice: `ix_linguistic_versatility_rounds_session_id` para joins por sesión.

## Manejo de errores

- **Gemini falla** → `VersatilityGeminiError` → router responde 502 con el mensaje + rollback de la transacción.
- **Audio > 5 MB** → 413 antes de tocar Gemini (no quemamos tokens en payloads basura).
- **UUID inválido en question_id o session_id** → 404 (no 500).
- **Sesión inexistente o de otro usuario** → 404 (sin distinción para no leakear existencia).
- **Excepción genérica** durante save → rollback explícito + re-raise.

## Decisiones de diseño

### Por qué Gemini multimodal en lugar de Whisper + LLM
Una sola llamada en lugar de dos servicios distintos. Gemini 2.5 Flash es competitivo en transcripción y análisis combinado, y ya está integrado en otros módulos. Reduce latencia y operación.

### Por qué `vocabulary_richness` como int
Permite agregaciones (promedio, modo) en analytics sin parsear strings, mantiene la columna pequeña, y el frontend mapea a labels traducidos en una constante (`{1: 'Básico', 2: 'Intermedio', 3: 'Avanzado'}`).

### Por qué no guardamos transcripción
Privacidad y storage. El usuario obtiene el feedback inmediato en pantalla; persistir el texto crudo aporta poco valor frente al riesgo de exponer contenido sensible.

### Por qué guardar rounds aunque sean ininteligibles
La sesión queda completa en el historial; el usuario ve qué intentó. Solo no incrementan `completed_rounds`, así no se cuenta hacia el promedio del puntaje final.

### Por qué selección de preguntas evita las recientes
Un usuario que practica diariamente no debería ver las mismas 3 preguntas todas las veces. Se filtran las usadas en sus últimas N sesiones; si no hay suficientes "frescas", cae a cualquier activa.
