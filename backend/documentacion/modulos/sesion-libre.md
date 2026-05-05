# Módulo: Sesión Libre

## Qué hace el módulo

El módulo de Sesión Libre permite al usuario hablar libremente en español mientras el sistema analiza su habla en tiempo real. El análisis cubre hasta tres dimensiones: pronunciación, acentuación y muletillas. El usuario recibe retroalimentación periódica cada 5 segundos mientras habla, y la sesión termina cuando se alcanza alguna condición de parada (error acumulado, puntuación baja, tiempo límite o cierre voluntario).

El módulo resuelve el problema de evaluar habla espontánea sin guión, a diferencia de las sesiones guiadas donde el usuario lee un texto predefinido. El flujo es: el cliente envía audio PCM en tiempo real vía WebSocket, el servidor lo reenvía a Gemini Live API y dispara análisis cada 5 segundos, y el servidor evalúa umbrales para decidir si continuar o terminar.

---

## Archivos del módulo

| Archivo | Responsabilidad |
|---|---|
| `app/presentation/routers/live_session.py` | Router WebSocket y endpoint REST de listado. Orquesta las tres corutinas concurrentes (audio, timer de análisis, timer de límite). |
| `app/use_cases/live_session/session_manager.py` | Estado en memoria de la sesión activa (`LiveSessionState`). Acumula errores, evalúa umbrales y calcula el promedio de puntajes. |
| `app/use_cases/live_session/prompt_builder.py` | Construye el prompt de sistema para Gemini según las dimensiones seleccionadas. Cada dimensión activa una sección de análisis y una clave en el bloque de respuesta. |
| `app/use_cases/live_session/save_session.py` | Persiste la sesión al cerrar. También provee `list_live_sessions` para el endpoint GET. |
| `app/infrastructure/ai/live_gemini.py` | Envuelve la Gemini Live API: abre la sesión, reenvía audio, dispara turnos y parsea el bloque `[EVAL]`. |
| `app/domain/entities/live_session.py` | Entidad SQLAlchemy `live_sessions`. Almacena todas las dimensiones seleccionadas, los ciclos de análisis en JSONB y el motivo de parada. |
| `app/presentation/schemas/live_session.py` | Esquemas Pydantic para respuestas REST (`LiveSessionListItem`, `LiveSessionResponse`). |

---

## Protocolo WebSocket

### Conexión

```
ws://<host>/live/session?token=<JWT>
```

El JWT se pasa como query param porque los navegadores no permiten enviar headers personalizados en conexiones WebSocket nativas.

### Flujo de mensajes

#### 1. Mensaje de inicio (cliente → servidor)

Enviado inmediatamente al abrir la conexión. El servidor espera máximo 10 segundos.

```json
{
  "type": "start",
  "dims": ["pron", "acc", "mul"]
}
```

Valores válidos para `dims`: `"pron"` (pronunciación), `"acc"` (acentuación), `"mul"` (muletillas). Se puede enviar uno, dos o los tres. Si `dims` está vacío o contiene un valor inválido, el servidor cierra con código `4003`.

#### 2. Ready (servidor → cliente)

```json
{ "type": "ready" }
```

Indica que Gemini está conectado y el servidor está listo para recibir audio.

#### 3. Audio (cliente → servidor)

Frames binarios PCM de 16 bits, 16 kHz, monocanal. No hay un mensaje JSON para esto; se envían directamente como frames binarios de WebSocket.

#### 4. Analysis (servidor → cliente)

Enviado cada 5 segundos mientras la sesión está activa.

```json
{
  "type": "analysis",
  "data": {
    "dims": {
      "pron": { "sc": 85, "err": [{ "ph": "/r/", "w": "pero", "fix": "vibración simple" }] },
      "acc": { "sc": 90, "err": [] },
      "mul": { "sc": 70, "det": [{ "w": "o sea", "n": 3 }] }
    },
    "overall": 82,
    "fb": "Buena pronunciación general, reduce el uso de muletillas."
  }
}
```

#### 5. Correction (servidor → cliente)

Enviado únicamente cuando se activa un umbral de parada por `low_score` o `error_threshold`. Va seguido inmediatamente del mensaje `session_ended`.

```json
{
  "type": "correction",
  "dim": "pron",
  "reason": "low_score",
  "errors": [{ "ph": "/rr/", "w": "carro", "fix": "vibración múltiple" }]
}
```

El campo `dim` es `null` cuando `reason` es `"error_threshold"` (los errores no se atribuyen a una sola dimensión).

#### 6. End voluntario (cliente → servidor)

```json
{ "type": "end" }
```

El cliente puede enviar este mensaje en cualquier momento para terminar la sesión.

#### 7. Session ended (servidor → cliente)

```json
{
  "type": "session_ended",
  "reason": "<motivo>"
}
```

Valores posibles de `reason`:

| Valor | Significado |
|---|---|
| `user_ended` | El cliente envió `{"type":"end"}` o desconectó |
| `low_score` | Un ciclo tuvo puntaje menor a 70 en alguna dimensión |
| `error_threshold` | Los errores acumulados llegaron a 3 o más |
| `time_limit` | La sesión alcanzó el máximo de 5 minutos |

#### 8. Error (servidor → cliente)

Solo se envía si la conexión con Gemini falla al abrir la sesión.

```json
{
  "type": "error",
  "message": "Error al conectar con el servicio de análisis"
}
```

### Códigos de cierre WebSocket

| Código | Motivo |
|---|---|
| `4001` | Token inválido o usuario inactivo |
| `4002` | No se recibió el mensaje de inicio en 10 segundos |
| `4003` | `dims` vacío o con valores inválidos |

---

## Lógica de umbrales

La evaluación ocurre en `LiveSessionState.evaluate_thresholds()` después de cada ciclo de análisis (cada 5 segundos). Se evalúan en este orden:

### 1. Puntaje bajo (`low_score`)

**Condición:** cualquier dimensión seleccionada tiene `sc < 70` en el ciclo actual.

**Acción:** se envía `correction` con la dimensión fallida y sus errores, luego `session_ended`. La sesión se interrumpe para corregir el problema antes de continuar.

**Razón del orden:** se evalúa primero porque un puntaje bajo en un solo ciclo es la señal más directa de un problema puntual grave. Tiene prioridad sobre el umbral de errores acumulados.

### 2. Umbral de errores (`error_threshold`)

**Condición:** `accumulated_errors >= 3`. Los errores de todas las dimensiones y todos los ciclos se suman.

**Acción:** se envía `correction` con `dim: null` (no se atribuye a una sola dimensión), luego `session_ended`.

**Razón:** el conteo acumulado detecta patrones de error persistentes aunque ningún ciclo individual baje de 70. Un usuario puede tener puntajes mediocres constantemente sin nunca llegar al umbral de `low_score`.

### 3. Tiempo límite (`time_limit`)

**Condición:** `elapsed_seconds() >= 300` (5 minutos).

**Evaluado en dos lugares:** dentro de `evaluate_thresholds()` como condición de respaldo, y en la corutina `session_limit_timer()` como temporizador independiente. El temporizador garantiza que el límite se respeta aunque no haya habido ningún ciclo de análisis reciente.

**Acción:** `session_ended` con `reason: "time_limit"`. No se envía `correction` porque no hay un error específico que señalar.

### 4. Cierre voluntario (`user_ended`)

**Condición:** el cliente envía `{"type":"end"}` o cierra la conexión WebSocket.

**Acción:** `stop_event` se activa, el bloque `finally` del router persiste la sesión y envía `session_ended`.

---

## Integración con Gemini Live API

### Modelo utilizado

`gemini-2.5-flash`. Se eligió Flash sobre Pro por latencia: el análisis debe completarse dentro de los 5 segundos del timer para no bloquear el siguiente ciclo. Flash tiene menor tiempo de respuesta con calidad suficiente para análisis de habla en segmentos cortos.

### Por qué VAD está deshabilitado

VAD (Voice Activity Detection) nativo de Gemini cierra automáticamente el turno cuando detecta silencio. Esto es incompatible con el modelo de sesión libre: el usuario puede hacer pausas naturales al hablar sin que eso deba disparar un análisis. El control de turno lo maneja el servidor mediante el timer de 5 segundos, que es predecible y configurable.

La desactivación se configura en `LiveConnectConfig`:

```python
realtime_input_config=types.RealtimeInputConfig(
    automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
)
```

### Cómo funciona el ciclo de análisis

1. `analysis_timer()` espera 5 segundos.
2. Llama a `gemini.trigger_analysis()`, que envía un turno vacío con `turn_complete=True`. Esto le indica a Gemini que el segmento terminó y debe responder.
3. Llama a `gemini.receive_analysis()`, que acumula tokens de respuesta hasta recibir `turn_complete` del servidor.
4. Parsea el bloque `[EVAL]` de la respuesta.

### Por qué se usan marcadores `[EVAL]`

Gemini Live API devuelve texto en streaming token por token. No existe un mecanismo nativo para indicar que la respuesta es JSON estructurado. Al envolver el JSON en `[EVAL]...[/EVAL]`, el parser puede extraer el bloque con una expresión regular aunque el modelo incluya texto adicional antes o después (lo cual puede ocurrir aunque el prompt lo prohíba explícitamente).

JSON puro sin marcadores fallaría si el modelo emite un prefacio o una disculpa antes del JSON. Los marcadores son robustos frente a variaciones en la generación.

El patrón de extracción es: `\[EVAL\](.*?)\[/EVAL\]` con flag `re.DOTALL`.

---

## Persistencia

La sesión se guarda **una sola vez al cerrar**, en el bloque `finally` del router. No se escribe en base de datos durante los ciclos de análisis.

### Qué se persiste

| Campo | Fuente |
|---|---|
| `user_id` | Usuario autenticado |
| `selected_dims` | Mensaje de inicio del cliente |
| `analyses` | Lista de todos los dicts parseados de `[EVAL]` durante la sesión |
| `overall_score` | Promedio de `overall` en todos los ciclos |
| `total_errors` | `accumulated_errors` de `LiveSessionState` |
| `duration_seconds` | `elapsed_seconds()` al momento de guardar |
| `stop_reason` | Razón final de parada |

### Por qué guardar al cerrar y no por ciclo

Guardar por ciclo implicaría N escrituras a la base de datos por sesión (una cada 5 segundos durante hasta 5 minutos = hasta 60 escrituras). Esto genera contención innecesaria en la base de datos y complejidad de manejo de errores durante la sesión activa.

La información de cada ciclo se acumula en memoria en `LiveSessionState.analyses` y se persiste en una sola transacción al final. Si la persistencia falla, se loguea el error pero no interrumpe el envío del mensaje `session_ended` al cliente.

---

## Decisiones de diseño

### Timer de 5 segundos vs VAD nativo

El VAD nativo de Gemini cierra el turno al detectar silencio, lo que es correcto para conversaciones pero incorrecto para habla espontánea con pausas. El timer de 5 segundos garantiza ciclos predecibles independientemente del ritmo del hablante. El intervalo se define en la constante `ANALYSIS_INTERVAL_SECONDS = 5` en el router.

### `[EVAL]` markers vs JSON puro

Gemini puede emitir texto antes o después del JSON aunque el prompt lo prohíba. Los marcadores permiten extraer el bloque estructurado de forma robusta sin asumir que la respuesta completa es JSON válido. El costo es un parser con regex, que es mínimo comparado con la fragilidad de asumir output puro.

### Guardar al cerrar vs guardar por ciclo

Una sesión de 5 minutos podría generar hasta 60 escrituras si se persistiera por ciclo. El modelo fire-on-close reduce la escritura a una sola transacción. El estado intermedio vive en `LiveSessionState` en memoria, que es suficiente dado que la sesión tiene duración máxima acotada y corre en un solo proceso.

### Auth por query param `?token=JWT` vs HTTPBearer para WebSocket

Los navegadores no permiten enviar headers personalizados (como `Authorization: Bearer ...`) al abrir conexiones WebSocket nativas. La única forma de pasar credenciales en el handshake inicial es a través de query params o cookies. Se eligió query param porque no requiere configuración de cookies en el cliente y es compatible con la infraestructura JWT existente del proyecto.

El token se valida en `_authenticate_ws()` antes de procesar cualquier mensaje. Si la validación falla, el servidor cierra con código `4001` sin procesar nada más.

---

## Restricciones conocidas

- **Límite de 5 minutos:** `MAX_DURATION_SEC = 300`. Una sesión no puede exceder este tiempo. Si se necesita más tiempo en el futuro, cambiar esta constante en `session_manager.py`.
- **Máximo 3 errores acumulados:** `MAX_ERRORS = 3`. El conteo incluye errores de todas las dimensiones en todos los ciclos. Un ciclo con 2 errores de pronunciación y 1 de acentuación suma 3 y termina la sesión.
- **Puntaje mínimo de 70:** `MIN_SCORE = 70`. Cualquier dimensión con `sc < 70` en un solo ciclo termina la sesión. Este umbral es estricto por diseño: el objetivo es que el usuario mantenga calidad consistente, no que promedia bien.
- **Formato de audio:** el cliente debe enviar PCM crudo de 16 bits, 16 kHz, monocanal. Otros formatos o tasas de muestreo producirán análisis incorrectos sin error explícito del servidor.
- **Dimensiones válidas:** `"pron"`, `"acc"`, `"mul"`. El servidor rechaza la sesión si se envía cualquier otro valor.
- **Concurrencia:** cada conexión WebSocket crea su propia instancia de `GeminiLiveService` y `LiveSessionState`. No existe estado compartido entre sesiones.
