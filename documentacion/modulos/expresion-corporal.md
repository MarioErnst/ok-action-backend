# Expresión Corporal — Documentación Backend

## 1. Descripción funcional

El módulo de Expresión Corporal registra métricas agregadas de presencia corporal durante una respuesta oral guiada. El frontend usa MediaPipe Pose Landmarker en el navegador para leer puntos del cuerpo y calcular postura, apertura, gesticulación, estabilidad, energía y encuadre.

El backend no procesa video ni landmarks. Solo recibe métricas agregadas, valida que la sesión tenga duración y tracking suficientes, persiste el resultado bajo el esquema uniforme y genera feedback efímero para la respuesta inmediata.

## 2. Capas del módulo

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Router | `backend/app/presentation/routers/body_expression.py` | Endpoints HTTP y mapeo de errores. |
| Schemas | `backend/app/presentation/schemas/body_expression.py` | Contratos Pydantic, validación de duración y tracking. |
| Use cases | `backend/app/use_cases/body_expression/sessions.py` | Score canónico, persistencia y feedback efímero. |
| Entidades | `backend/app/domain/entities/body_expression_metrics.py` | Métricas 1:1 asociadas a `sessions`. |
| AI | `backend/app/infrastructure/ai/body_expression_gemini.py` | Feedback opcional con Gemini a partir de métricas agregadas. |

## 3. Modelo de datos

Una sesión se representa con dos filas: `sessions` raíz y `body_expression_metrics` 1:1.

### `sessions`

Para expresión corporal standalone: `module='body_expression'`, `parent_id=NULL`, `status='completed'`. `score` lo deriva el backend con la fórmula canónica del módulo.

### `body_expression_metrics`

| Columna | Tipo | Restricciones | Descripción |
|---------|------|---------------|-------------|
| `session_id` | UUID | PK / FK `sessions.id` ON DELETE CASCADE | Vínculo 1:1. |
| `posture_score` | SMALLINT | 0-100 | Alineación de hombros y torso. |
| `openness_score` | SMALLINT | 0-100 | Apertura corporal y brazos no cerrados. |
| `gesture_score` | SMALLINT | 0-100 | Gesticulación útil, ni ausente ni excesiva. |
| `stability_score` | SMALLINT | 0-100 | Control del movimiento corporal. |
| `energy_score` | SMALLINT | 0-100 | Presencia física y dinamismo. |
| `framing_score` | SMALLINT | 0-100 | Calidad de encuadre/cámara. |
| `tracked_pct` | SMALLINT | 0-100 | Porcentaje de frames con pose válida. |
| `hands_visible_pct` | SMALLINT | 0-100 | Porcentaje de frames con manos visibles. |
| `excessive_movement_pct` | SMALLINT | 0-100 | Porcentaje de frames con movimiento distractor. |
| `calibration_quality_pct` | SMALLINT | 0-100 | Calidad de la calibración inicial. |
| `framing_mode` | body_framing_mode_enum | NOT NULL | `upper_body`, `full_body` o `mixed`. |

## 4. Esquemas de solicitud y respuesta

### Entrada

`BodyExpressionSessionCreate` recibe:

- `started_at`
- `ended_at`
- `prompt_text`
- `metrics`
- `parent_id` opcional, reservado para una futura composición live.

Validaciones:

- `ended_at > started_at`
- duración mínima de 20 segundos
- `tracked_pct >= 40`
- todos los scores y porcentajes entre 0 y 100

### Salida

`BodyExpressionSessionDetail` devuelve datos de `sessions`, métricas persistidas y `feedback` efímero. El feedback no se guarda en base de datos.

`BodyExpressionSessionListItem` expone un resumen compacto para histórico.

## 5. Casos de uso

### `derive_body_expression_score(metrics)`

Fórmula canónica:

```text
score =
  posture_score * 0.20 +
  openness_score * 0.20 +
  gesture_score * 0.20 +
  stability_score * 0.15 +
  energy_score * 0.15 +
  framing_score * 0.10
```

El resultado se redondea y se limita a 0-100. `sessions.score` usa este valor.

### `create_body_expression_session(db, user, payload)`

Inserta `sessions(module='body_expression')` y `body_expression_metrics` en una transacción. Después del commit genera feedback efímero. Si Gemini falla, se usa feedback por reglas.

### `list_body_expression_sessions(db, user)`

Lista sesiones standalone (`parent_id IS NULL`) ordenadas por `started_at DESC`.

### `get_body_expression_session(db, user, session_id)`

Devuelve detalle del usuario autenticado o `None` para 404.

## 6. Integración con Gemini AI

Gemini recibe solo métricas agregadas y la consigna oral. No recibe video, audio, landmarks ni transcripción. El prompt le exige no inventar acciones observadas y producir feedback breve, accionable y en español.

El resultado de Gemini es efímero:

- se incluye en la respuesta inmediata del `POST`;
- no se persiste;
- si falla o excede timeout, se reemplaza por feedback determinístico por reglas.

## 7. Endpoints de la API

- `POST /body-expression/sessions` → crea sesión, persiste métricas y devuelve feedback.
- `GET /body-expression/sessions` → lista histórico standalone.
- `GET /body-expression/sessions/{session_id}` → detalle de sesión.

Todos requieren Bearer JWT.

## Nota sobre sesión libre

El módulo no se integra todavía a `live-session`, porque el live actual procesa audio y módulos derivados de audio. Expresión corporal requiere captura visual paralela. La tabla y el schema ya dejan preparada la posibilidad de usar `parent_id` en una integración futura.
