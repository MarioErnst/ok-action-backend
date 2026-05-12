# Fluidez — Documentación Backend

## 1. Descripción funcional

El módulo de Fluidez evalúa la continuidad del habla del usuario en tiempo real mientras responde a una consigna. Es **el primer módulo basado en WebSocket** del producto: el cliente abre un canal full-duplex, manda audio en streaming, y el backend lo analiza por segmentos cada 5 segundos llamando a Gemini.

Flujo:

1. Cliente abre WS en `/fluency/session?token=<jwt>`.
2. Cliente envía `{type: "start", prompt_text: "..."}` (timeout: 10s).
3. Backend responde `{type: "ready"}`.
4. Cliente streamea bytes de audio (PCM 16k mono).
5. Cada 5s backend llama Gemini con el chunk acumulado, manda `{type: "analysis", data}` y eventualmente `{type: "warning", reason, data}`.
6. Cliente termina con `{type: "end"}`, o se desconecta, o se alcanza el límite (120s).
7. Backend persiste 1 fila en `sessions` + 1 en `fluency_metrics` agregando todas las analyses, manda `{type: "session_ended", reason, average_score, session_id}` y cierra.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/fluency.py` | WebSocket lifecycle + endpoints HTTP de history. Persistencia al cierre. |
| Schemas | `backend/app/presentation/schemas/fluency.py` | Contratos Pydantic v2 de los endpoints HTTP. El protocolo WS usa JSON arbitrario. |
| Use cases | `backend/app/use_cases/fluency/sessions.py`, `session_manager.py`, `prompt_builder.py` | Persistencia + agregación + estado en memoria de la sesión + construcción del prompt Gemini. |
| Infra AI | `backend/app/infrastructure/ai/fluency_gemini.py` | Cliente Gemini con schema endurecido (scores INTEGER). |
| Entidades | `backend/app/domain/entities/session.py`, `fluency_metrics.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

### `sessions` (raíz, compartida)

Para fluency standalone: `module='fluency'`, `parent_id=NULL`. **Solo se inserta la fila al cierre del WS** (a diferencia de precision/linguistic_versatility que abren la fila como `active`).

`status`: `completed` si terminó normal (`user_ended` o `time_limit`), `aborted` si hubo disconnect/error.

`score` derivado = avg de `score` overall de cada analysis Gemini.

### `fluency_metrics` (1:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `fluency_score` | SMALLINT | NOT NULL, CHECK 0-100 | Avg de `fluency_score` de cada analysis. |
| `stuck_events_count` | INT | NOT NULL DEFAULT 0 | Suma de `len(stuck_events) + repetitions + restarts + long_blocks` cross analyses. Definición ampliada de "stuck". |
| `words_per_minute` | NUMERIC(6,2) | NOT NULL DEFAULT 0 | Avg de `wpm` por analysis. |

### Decisiones de diseño

- **Persistencia solo al cierre**: el JSON propuesta dice "Persistir al cierre `session_ended`: 1 fila en `sessions` + 1 en `fluency_metrics`. Sin tabla hija." A diferencia de precision/linguistic_versatility, fluency no inserta al inicio; si el cliente se conecta y se desconecta sin grabar, no queda fila en BD. Mantiene la tabla limpia de sesiones vacías.
- **`analyses` JSONB eliminado** (vivía en `live_sessions.analyses` viejo): texto de cada chunk Gemini sin valor longitudinal. Solo agregados.
- **Drops LLM**: `feedback`/`fb`, `strengths`, `improvement_areas`, `pace_feedback`, `transcript`. Llegan al cliente en cada `{type: "analysis"}` para UI en vivo, no se persisten.
- **`stuck_events_count` interpretación amplia** = stuck_events + repetitions + restarts + long_blocks. Matchea la definición que el OLD `evaluate_attention` usaba para emitir warnings; mantiene el significado al usuario constante.
- **`score` (sessions) = avg de `score` overall por analysis**, NO igual a `fluency_score` (que es el sub-score específico de continuidad). Frontend muestra ambos en distintos contextos.
- **`words_per_minute` = avg simple por analysis**, no ponderado por duración del chunk. Los chunks tienen tamaño consistente (5s) por la cadencia del timer; el sesgo es despreciable. Si en el futuro el timer cambia a chunks variables, considerar weighted avg.
- **Sin `stop_reason` persistido**: el JSON solo lo incluye en `live_metrics`. Para fluency, mapeamos a `status` y descartamos el specific reason. Si en el futuro se quiere distinguir time_limit vs user_ended en analytics, agregar columna.
- **Empty session policy**: si el WS terminó sin ninguna analysis (cliente abrió y cerró), `persist_fluency_session` retorna None y no escribe nada. El `session_ended` enviado al cliente lleva `session_id: null`.
- **Schema Gemini endurecido**: 6 score fields cambiados de `"number"` a `"integer"` preemptive (lección compartida desde precision/accentuation reviews).
- **Auth WS**: el token JWT viene en query string (los WS browser no soportan headers custom durante el handshake). `authenticate_ws` valida sin levantar excepción HTTP — retorna user|None y el handler cierra con código 4001 si None.
- **Sesión de DB private para auth y persist**: el WS lifecycle es largo; usar `get_session` request-scoped la mantendría abierta minutos. En vez, abrimos `async_session_factory()` en context manager solo para la auth y luego para la persistencia final, sin tocar DB durante el streaming.

## 4. Esquemas

### Salida HTTP

`FluencyMetricsOutput`: `fluency_score`, `stuck_events_count`, `words_per_minute` (float).

`FluencySessionDetail`: `id`, `user_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`, `metrics`.

`FluencySessionListItem` (compacto): `id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `fluency_score`, `words_per_minute`. Trae las dos métricas más informativas para una card de timeline.

### Protocolo WS (JSON arbitrario, no schemas Pydantic)

Cliente → servidor:
- `{"type": "start", "prompt_text": "..."}`
- bytes (audio)
- `{"type": "end"}`

Servidor → cliente:
- `{"type": "ready"}`
- `{"type": "analysis", "data": {...}}` (cada 5s)
- `{"type": "warning", "reason": "...", "data": {...}}` (si la heurística dispara)
- `{"type": "session_ended", "reason": "user_ended|time_limit|...", "average_score": N|null, "session_id": UUID|null}`

## 5. Casos de uso

### `_aggregate_analyses(analyses)` — `sessions.py`

Reduce la lista de chunks Gemini a `(score, fluency_score, stuck_events_count, words_per_minute)`. Si la lista está vacía retorna ceros (caller decide qué hacer).

### `persist_fluency_session(db, user, started_at, ended_at, status, analyses)` — `sessions.py`

Inserta `sessions(module='fluency')` + `fluency_metrics` 1:1 si hay analyses. Retorna None si no hay para no spam-ear historia con sesiones vacías.

### `list_fluency_sessions(db, user)`, `get_fluency_session(db, user, session_id)` — `sessions.py`

Patrón idéntico a otros módulos: JOIN session+metrics, filter `parent_id IS NULL`, 404 para no-encontrado o cross-user.

### `FluencySessionState` — `session_manager.py`

Estado en memoria de la WS session. Campos: `prompt_text`, `analyses` (lista cruda de chunks Gemini), `started_at`, `stop_reason`. Métodos: `evaluate_attention(analysis) -> (should_warn, reason)` para decidir warnings al cliente.

### `build_fluency_prompt(prompt_text)` — `prompt_builder.py`

Construye el prompt Gemini insertando la consigna del usuario.

## 6. Endpoints

- `WS /fluency/session?token=<jwt>` — protocolo descrito arriba. Códigos de cierre WS:
  - 4001: Unauthorized (auth fallida)
  - 4002: Expected start message (timeout o malformado)
  - normal close: tras enviar `session_ended`.
- `GET /fluency/sessions` → 200, lista standalone ordenada por `started_at DESC`. Bearer JWT.
- `GET /fluency/sessions/{id}` → 200 / 404. Bearer JWT.

## 7. Pendientes en el roadmap

- **Composición en sesión live**: `persist_fluency_session` debe aceptar `parent_id` opcional cuando lo invoque el orquestador del módulo `live`. La autenticación tendrá que aceptar el live_id como contexto.
- **`stop_reason` persistido**: si las analytics necesitan distinguir `user_ended` vs `time_limit` vs `disconnect`, agregar columna `fluency_metrics.stop_reason`.
- **Weighted wpm**: si el timer pasa a chunks variables, cambiar `_aggregate_analyses` a promedio ponderado por duración del chunk.
- **Gemini schema range**: hardening adicional sería añadir `minimum`/`maximum` 0-100 al schema Gemini para que un score fuera de rango falle en Gemini en vez de provocar IntegrityError en BD.
- **MIME WS**: hoy el cliente debe mandar PCM 16k mono. No hay validación; si manda otro formato, Gemini puede rechazar silenciosamente.
