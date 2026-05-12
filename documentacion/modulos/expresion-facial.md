# Expresión Facial — Documentación Backend

## 1. Descripción funcional

El módulo de Expresión Facial registra cuán expresivo es el usuario al hablar. El frontend usa modelos ML en el cliente para detectar la emoción dominante frame por frame durante la sesión, agrega el tiempo en cada emoción, y al cierre envía las 7 distribuciones porcentuales al backend.

El backend tiene dos responsabilidades:

1. Persistir las 7 distribuciones bajo el esquema unificado.
2. Derivar `top_emotion` y `expressiveness_score` con fórmulas canónicas.
3. Exponer el histórico standalone del usuario.

No procesa video ni hace ML; toda la detección facial vive en frontend.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/facial_expression.py` | Endpoints HTTP, mapeo de errores. |
| Schemas | `backend/app/presentation/schemas/facial_expression.py` | Contratos Pydantic v2 con validación de suma=100. |
| Use cases | `backend/app/use_cases/facial_expression/sessions.py` | Persistencia y derivaciones (`top_emotion`, `expressiveness_score`). |
| Entidades | `backend/app/domain/entities/session.py`, `facial_expression_metrics.py` | Modelo SQLAlchemy del esquema uniforme. |

## 3. Modelo de datos

Una sesión se representa con dos filas: `sessions` raíz y `facial_expression_metrics` 1:1.

### `sessions` (raíz, compartida)

Para facial_expression standalone: `module='facial_expression'`, `parent_id=NULL`, `status='completed'`. `score` lo deriva el backend = `expressiveness_score`.

### `facial_expression_metrics` (1:1 con `sessions`)

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `expressiveness_score` | SMALLINT | NOT NULL, CHECK 0-100 | Derivado: `100 - neutral_pct`. |
| `top_emotion` | top_emotion_enum | NOT NULL | Derivada: emoción con mayor pct (tie-break por orden de enum). |
| `happy_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % tiempo expresando alegría. |
| `sad_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % tiempo expresando tristeza. |
| `angry_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % tiempo expresando enojo. |
| `surprised_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % tiempo expresando sorpresa. |
| `fearful_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % tiempo expresando temor. |
| `disgusted_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % tiempo expresando disgusto. |
| `neutral_pct` | SMALLINT | NOT NULL, CHECK 0-100 | % tiempo neutral (sin emoción dominante). |

CHECK adicional: las 7 columnas suman exactamente 100.

### Decisiones de diseño

- **Tabla `facial_expression_emotion_events` eliminada**: el timeline de eventos de cambio de emoción servía para un eventual replay UI que nunca se construyó. El nuevo diseño solo persiste la distribución agregada, que es lo único que se usa longitudinalmente.
- **`emotion_distribution JSONB` reemplazada por 7 columnas explícitas**: queryable, indexable, tipada con CHECK individual + CHECK de suma. Ningún JSONB caja-de-sastre.
- **`top_emotion` derivado en backend**: max de los 7 pcts. Tie-break por orden enum (happy > sad > angry > surprised > fearful > disgusted > neutral) — pensado para que en empates con neutral gane la emoción expresiva, que es lo más útil mostrarle al usuario.
- **`expressiveness_score` derivado en backend = `100 - neutral_pct`**: fórmula canónica simple ("entre menos neutral, más expresivo"). Precedente loudness/accentuation. Si quieres una fórmula más nuanced (variedad, intensidad, picos), cambia en `_derive_expressiveness_score` en un solo lugar.
- **`score` (sessions) = `expressiveness_score`**: misma magnitud, una sola fuente de verdad. Frontend muestra siempre lo mismo en cualquier vista.
- **Renombre de emociones contra el viejo schema**: el esquema viejo usaba `surprise/fear/disgust`, el nuevo usa `surprised/fearful/disgusted` para alinear con el ENUM nativo `top_emotion_enum`. Ruptura de contrato; frontend tiene que adaptarse en Fase 4.
- **`gestures` (free-form dict por evento) eliminado**: parte de la tabla de eventos descartada, sin uso analítico.
- **URL kebab `/facial-expression`**: convención web para multi-palabras. El module enum interno sigue snake (`facial_expression`); no se mezclan contextos.

## 4. Esquemas

### Entrada

`FacialExpressionMetricsInput`: 7 `*_pct` (cada 0-100). Validador `validate_pct_sum` chequea que sumen 100.

`FacialExpressionSessionCreate`: `started_at`, `ended_at`, `metrics`. Validador `validate_time_range` chequea `ended_at > started_at`. **Sin `expressiveness_score`, `top_emotion` ni `score`**: backend los deriva.

### Salida

`FacialExpressionMetricsOutput`: 7 `*_pct` + `expressiveness_score` + `top_emotion`.

`FacialExpressionSessionDetail`: `id`, `user_id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `created_at`, `metrics`.

`FacialExpressionSessionListItem` (compacto): `id`, `started_at`, `ended_at`, `duration_ms`, `score`, `status`, `top_emotion`, `expressiveness_score`. Ambos derivados expuestos para que el card del timeline muestre el resumen.

## 5. Casos de uso

### `_derive_top_emotion(payload)` — `sessions.py`

Construye un dict `{TopEmotionEnum: pct}` y aplica `max(_EMOTION_ORDER, key=lambda e: pcts[e])`. El argumento `key` desempata por orden definido en `_EMOTION_ORDER`.

### `_derive_expressiveness_score(payload)` — `sessions.py`

`100 - neutral_pct`. Una línea, separada en función para que el cambio de fórmula sea trivial.

### `create_facial_expression_session(db, user, payload)`

En una transacción inserta `sessions(module='facial_expression', status='completed', parent_id=NULL)` con `duration_ms`/`score` derivados + `facial_expression_metrics` con `expressiveness_score`/`top_emotion` derivados y las 7 pct copiadas del input.

### `list_facial_expression_sessions(db, user)`

JOIN `sessions + facial_expression_metrics`, filtra `module='facial_expression' AND parent_id IS NULL`, ordena por `started_at DESC`.

### `get_facial_expression_session(db, user, session_id)`

Detalle. Retorna `None` para no-encontrado o cross-user (router → 404 sin distinguir).

## 6. Endpoints

- `POST /facial-expression/sessions` → 201 / 422 (incluye 422 si las 7 pct no suman 100).
- `GET /facial-expression/sessions` → 200, lista standalone ordenada por `started_at DESC`.
- `GET /facial-expression/sessions/{id}` → 200 / 404.

Todos requieren Bearer JWT.

## 7. Pendientes en el roadmap

- **Composición en sesión live**: cuando se reescriba `live`, `create_facial_expression_session` debe aceptar `parent_id` opcional.
- **Sesiones abortadas**: hoy solo `status='completed'`.
- **Replay UI**: si en el futuro se implementa replay frame-a-frame, hay que reintroducir una tabla de eventos (no la vieja, una nueva con `t_ms` + `top_emotion` solamente). Por ahora no aporta.
