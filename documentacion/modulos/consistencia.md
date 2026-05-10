# Consistencia — Documentación Backend

## 1. Descripción funcional

El módulo de Consistencia evalúa si el usuario mantiene un desempeño parejo de inicio a fin al hablar (ritmo, volumen, claridad, foco, confianza, estructura). Igual que fluency, usa **WebSocket**, pero a diferencia de éste hace **una sola llamada Gemini al cierre** sobre el buffer completo, no por chunks (Gemini necesita comparar inicio/medio/cierre como pieza única).

Flujo:

1. Cliente abre WS en `/consistency/session?token=<jwt>`.
2. Cliente envía `{type: "start", prompt_text: "..."}` (timeout: 10s).
3. Backend responde `{type: "ready"}`.
4. Cliente streamea bytes de audio (PCM 16k mono) hasta `{type: "end"}` o el límite (120s).
5. Backend evalúa el buffer completo con Gemini (una sola llamada).
6. Si el audio fue intelegible: persiste 1 fila `sessions` + 1 `consistency_metrics`. Manda `{type: "analysis", data}`, eventualmente `{type: "warning", reason, data}`, y `{type: "session_ended", reason, score, session_id}`.
7. Si el buffer fue muy corto o Gemini falló: no persiste nada; manda placeholder o error.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/consistency.py` | WebSocket lifecycle + endpoints HTTP de history. Llamada Gemini única al cierre. |
| Schemas | `backend/app/presentation/schemas/consistency.py` | Contratos Pydantic v2 de los endpoints HTTP. |
| Use cases | `backend/app/use_cases/consistency/sessions.py`, `session_manager.py`, `prompt_builder.py` | Persistencia + agregación + estado en memoria + prompt Gemini. |
| Infra AI | `backend/app/infrastructure/ai/consistency_gemini.py` | Cliente Gemini con schema endurecido (scores INTEGER + nuevo `active_pct`). |
| Entidades | `backend/app/domain/entities/session.py`, `consistency_metrics.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

### `sessions` (raíz, compartida)

Para consistency standalone: `module='consistency'`, `parent_id=NULL`. Solo se inserta al cierre del WS, igual que fluency.

`status`: `completed` si user_ended/time_limit, `aborted` si disconnect/error/unknown.

`score` derivado = `consistency_score` (= Gemini's overall `score`).

### `consistency_metrics` (1:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `consistency_score` | SMALLINT | NOT NULL, CHECK 0-100 | Score overall de Gemini, clampeado a [0,100]. |
| `volatility_score` | SMALLINT | NOT NULL, CHECK 0-100 | Derivado server-side: `max(0, 100 - len(volatility_events) * 20)`. 5+ eventos = 0. |
| `active_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % del audio en que el hablante estuvo emitiendo voz, según Gemini (campo nuevo agregado al prompt y schema). |

### Decisiones de diseño

- **Una sola llamada Gemini al cierre** (no per-chunk como fluency): el análisis de consistencia requiere comparar inicio/medio/cierre como pieza completa. Streaming + análisis incremental no aplica aquí.
- **`active_pct` campo nuevo agregado a Gemini**: el viejo schema Gemini no lo retornaba. Alternativa rechazada: derivarlo localmente con detector de silencio (heavy en async loop). Decidido: pedirle a Gemini que lo estime junto con los demás scores. Prompt y `_CONSISTENCY_SCHEMA` actualizados.
- **`volatility_score` derivado de `volatility_events` count**: server-side, fórmula `max(0, 100 - len*20)`. Captura "menos eventos = mayor score". Si quieres una métrica más fina (severidad ponderada por evento), cambia en `_derive_volatility_score`.
- **`consistency_score` = `score` de Gemini**: el score overall de Gemini ya se computa con la fórmula ponderada de los 6 sub-scores (rhythm, volume, clarity, focus, confidence, structure). Reusarlo evita duplicar la lógica en backend. Si frontend quiere una fórmula distinta, se cambia el prompt.
- **`session.score` = `consistency_score`**: misma magnitud, una sola fuente de verdad para todas las vistas.
- **Empty session policy + Gemini failure**: tres escenarios al cierre:
  - Buffer < MIN: usa `build_no_audio_analysis()` (placeholder con `audio_intelligible=false`); NO persiste.
  - Gemini falla (None): NO persiste, manda `{type: "error"}`.
  - Audio intelegible: persiste y manda `analysis + warning + session_ended`.
- **stop_reason → status mapping** con lecciones de fluency review:
  - user_ended/time_limit → completed
  - disconnect/error/unknown → aborted (default conservador)
  - explícitamente seteado en cada path en `stream_audio` (disconnect → "disconnect", exception → "error").
- **Drops per JSON**: `timeline`, `volatility_events` (después de derivar `volatility_score`), `classification`, `strengths`, `improvement_areas`, `recommendation`, `fb`, los 6 sub-scores intermedios. Solo los 3 scores finales se persisten.
- **Schema Gemini endurecido**: 7 score fields cambiados de `"number"` a `"integer"` preemptive + nuevo `active_pct: integer`.
- **Clamp [0,100] en backend** además del CHECK Postgres: `_clamp_pct` evita que un Gemini fuera de rango (improbable pero posible) reviente el insert.
- **Auth/persist con private DB session**: igual que fluency, evita mantener una conexión request-scoped abierta durante el streaming.

## 4. Esquemas

### Salida HTTP

`ConsistencyMetricsOutput`: `consistency_score`, `volatility_score`, `active_pct`.

`ConsistencySessionDetail`: `id`, `user_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`, `metrics`.

`ConsistencySessionListItem` (compacto): `id` + timeline meta + las 3 métricas de consistency. Suficiente para una card.

### Protocolo WS (JSON arbitrario, no schemas Pydantic)

Cliente → servidor:
- `{"type": "start", "prompt_text": "..."}`
- bytes (audio)
- `{"type": "end"}`

Servidor → cliente:
- `{"type": "ready"}`
- `{"type": "analysis", "data": {...}}` (al cierre, una sola)
- `{"type": "warning", "reason": "...", "data": {...}}` (si la heurística dispara)
- `{"type": "session_ended", "reason": "user_ended|time_limit|disconnect|error|unknown", "score": N|null, "session_id": UUID|null}`
- `{"type": "error", "message": "..."}` (si Gemini falló)

## 5. Casos de uso

### `_clamp_pct(value)`, `_safe_int(value, default)` — `sessions.py`

Helpers defensivos para evitar que un campo Gemini fuera de rango/tipo reviente el insert.

### `_derive_volatility_score(volatility_events)` — `sessions.py`

`max(0, 100 - len(events) * 20)`. Función separada para que el cambio de fórmula sea local.

### `_aggregate_analysis(analysis)` — `sessions.py`

Reduce el dict Gemini a `(overall, consistency, volatility, active)`. Aplica clamps y `_safe_int` en todos los campos.

### `persist_consistency_session(db, user, started_at, ended_at, status, analysis)` — `sessions.py`

Inserta `sessions(module='consistency')` + `consistency_metrics` 1:1 si `analysis` no es None. Retorna None si no hay nada que persistir.

### `list_consistency_sessions`, `get_consistency_session` — `sessions.py`

Patrón estándar: JOIN session+metrics, filter `parent_id IS NULL`, 404 para no-encontrado o cross-user.

### `ConsistencySessionState` — `session_manager.py`

Estado en memoria de la WS session. Campo `analysis` único (no lista, porque es una sola evaluación al final).

## 6. Endpoints

- `WS /consistency/session?token=<jwt>` — protocolo descrito arriba. Códigos de cierre WS:
  - 4001: Unauthorized
  - 4002: Expected start message
  - normal close: tras `session_ended` o `error`.
- `GET /consistency/sessions` → 200, lista standalone ordenada por `started_at DESC`. Bearer JWT.
- `GET /consistency/sessions/{id}` → 200 / 404. Bearer JWT.

## 7. Pendientes en el roadmap

- **Composición en sesión live**: `persist_consistency_session` debe aceptar `parent_id` opcional cuando lo invoque el orquestador del módulo `live`.
- **`stop_reason` persistido**: si las analytics necesitan distinguir reasons, agregar columna `consistency_metrics.stop_reason`.
- **`active_pct` validation**: hoy depende de la honestidad de Gemini. Si en el futuro se quiere triple-check, computar localmente con detector de silencio agregado y comparar.
- **Volatility severity weights**: hoy cuenta eventos planos. Si las analytics quieren ponderar severity (low/medium/high), expandir `_derive_volatility_score`.
- **MIME WS**: cliente debe mandar PCM 16k mono. Sin validación.
- **Gemini schema range**: agregar `minimum`/`maximum` 0-100 a los scores.
