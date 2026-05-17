# Sistema de Strikes en Sesión Live — Backend

A partir de la branch `feature/live_corten` (mayo 2026), el strike system se basa
en una conexión WebSocket bidireccional contra Gemini Live (`gemini-3.1-flash-live-preview`)
con function calling. Cada strike corresponde a UN tool call que el modelo emite
mientras escucha el audio del usuario en streaming. El umbral en el frontend pasa
a **1 strike = corten inmediato**.

La feature comparte nombre con la documentación frontend (`live-strike-system.md`).
Este archivo cubre solo los cambios backend.

## 1. Cambios funcionales respecto al pipeline anterior

| Aspecto | Antes (frame eval HTTP) | Ahora (Gemini Live WS) |
|---|---|---|
| Transporte | HTTP multipart por cada frame de 5-8s | WebSocket único por sesión, audio streaming continuo |
| Modelo | `gemini-2.5-flash` con response_schema | `gemini-3.1-flash-live-preview` con function tools |
| Detección | JSON estructurado por frame | Function call por error detectado (latencia sub-segundo) |
| Umbral strike | 2 strikes por categoría | 1 strike por categoría |
| Persistencia en vivo | Ninguna (frame eval era stateless) | Ninguna (los strikes son ephemeral) |

La detección facial (`facial_expression`) sigue 100% en cliente con MediaPipe.
El composed eval final (`POST /live/sessions/{id}/audio-evaluation`) sigue siendo
la única fuente de verdad para las hijas en BD; los strikes nunca se persisten.

## 2. Cambios en BD

Ninguno. El strike system es ephemeral. No hay migración asociada a esta versión.

`StopReasonEnum` mantiene `user_stop`, `time_limit`, `error`, `completed`,
`auto_stop_strikes`, `auto_stop_emotion`. La diferencia es que ahora
`auto_stop_strikes` se dispara con 1 strike en cualquier categoría.

## 3. Estructura de directorios

```
app/use_cases/live/
├── sessions.py                ← lifecycle existente (start, finalize, abandon)
├── composed/                  ← evaluación final (intacto)
│   ├── prompts.py
│   ├── schemas.py
│   └── persist.py
└── streaming/                 ← REEMPLAZADO
    ├── __init__.py
    ├── tools.py               ← declaraciones de function tools por módulo
    ├── live_prompt.py         ← system_instruction "evaluador silencioso"
    └── supervisor.py          ← orquestador WS-a-WS con filtro anti-alucinación

app/infrastructure/ai/
├── composed_live_gemini.py    ← intacto, sigue usando gemini-2.5-flash
└── live_stream_gemini.py      ← NUEVO, wrapper async sobre client.aio.live.connect

app/presentation/routers/
├── live.py                    ← endpoints HTTP del lifecycle (sin frame eval)
└── live_ws.py                 ← NUEVO, endpoint WS /live/sessions/{id}/stream
```

## 4. Protocolo WebSocket

`WS /api/live/sessions/{session_id}/stream?token=<JWT>`

```
client -> server: {"type": "start", "modules": ["muletillas", "pronunciation", ...]}
server -> client: {"type": "ready"}
client -> server: <bytes>                            # raw 16 kHz mono PCM
client -> server: {"type": "end"}                    # cierre voluntario
server -> client: {"type": "strike", "category": "muletillas", "word": "este",
                    "transcript_snippet": "...", "severity": "low",
                    "received_at_ms": 1736000000123}
server -> client: {"type": "session_ended"}
server: cierra WS
```

Close codes:
- `4001` Unauthorized (token inválido)
- `4002` Expected start message (no llegó dentro de 10s)
- `4003` Invalid parameters (modules vacío/inválido, session_id no es live activa)
- `4500` Internal error (supervisor falló)

El cliente debe seguir enviando audio hasta que decida `end` o reciba un `strike`
que dispare la lógica de corten en su lado. El backend no decide cuándo cortar;
solo emite cada strike válido para que el frontend lo cuente.

## 5. Tools declarados (`streaming/tools.py`)

Tres function declarations, cada una con `transcript_snippet` y `severity`
requeridos. Registry indexado por módulo + reverse lookup nombre→módulo:

| Tool name | Módulo | Args principales |
|---|---|---|
| `flag_muletilla` | muletillas | `word`, `transcript_snippet`, `severity` |
| `flag_pronunciation_error` | pronunciation | `word`, `phoneme`, `actual_issue`, `suggestion`, `transcript_snippet`, `severity` |
| `flag_accentuation_error` | accentuation | `word`, `expected_stress`, `actual_issue`, `suggestion`, `transcript_snippet`, `severity` |

`build_tools_for_modules(modules)` arma la lista en orden canónico para que el
payload a Gemini sea estable. Agregar un módulo nuevo = una entrada en el
registry y una sección en `live_prompt.py`.

## 6. System prompt (`streaming/live_prompt.py`)

Tres reglas duras le indican al modelo:

1. Solo emitir tool calls. Nunca audio. Nunca texto.
2. `transcript_snippet` debe contener 5-12 palabras realmente escuchadas. Calls
   sin snippet o con snippet menor a 4 caracteres se descartan en el supervisor.
3. No inferir errores que no se escucharon. Modelo debe quedarse en silencio si
   no hay nada que reportar.

El prompt se reconstruye por sesión a partir de la lista de módulos
seleccionados, así el modelo solo ve las tools que están wireadas.

## 7. Cliente Gemini Live (`infrastructure/ai/live_stream_gemini.py`)

Wrapper async sobre `client.aio.live.connect`. Una instancia = una WS abierta por
toda la duración de la sesión live.

Métodos:
- `open()` retorna un async context manager que entra/sale el WS limpio.
- `send_audio_chunk(pcm_bytes)` reenvía un blob PCM al modelo. Lock interno para
  serializar sends.
- `signal_audio_end()` notifica al modelo que el usuario dejó de hablar.
- `iter_tool_calls()` async generator que itera tool calls recibidos. Mensajes
  de texto del modelo se ignoran (response_modalities = TEXT pero el prompt pide
  silencio; cualquier texto se descarta).
- `ack_tool_call(call)` envía FunctionResponse vacío para que el modelo avance.

Config de la sesión:
- `response_modalities = [Modality.AUDIO]`. Los modelos Live de la Gemini
  Developer API (la que se usa con `api_key`) rechazan TEXT como única
  modalidad — solo Vertex AI ofrece la variante half-cascade que sí lo
  permite. Pedimos AUDIO y descartamos todo el output del modelo en
  `iter_tool_calls` (solo yield-eamos `tool_call`); el system prompt
  pide silencio así que el audio emitido tiende a ser un saludo corto a
  lo sumo.
- `system_instruction = build_live_streaming_prompt(modules)`.
- `realtime_input_config.automatic_activity_detection` con
  `end_of_speech_sensitivity=HIGH`, `silence_duration_ms=300`,
  `prefix_padding_ms=0`. El default de Gemini Live espera ~1 s de
  silencio para marcar fin de turno y procesar herramientas. Con un
  alumno que habla 20 s seguidos sin pausa larga, los tool calls
  quedan buffer-eados hasta el cierre del WS y el "corten" llega
  irremediablemente tarde. Forzando el VAD agresivo, cualquier pausa
  natural entre frases (200-500 ms en español espontáneo) ya cuenta
  como end-of-turn y dispara la emisión de strikes en near-real-time.
- `tools = [Tool(function_declarations=[FunctionDeclaration(**decl) for decl in build_tools_for_modules(modules)])]`.
- `temperature = 0.3` para limitar falsos positivos.

Sin retry. Si la WS de Gemini cae, el supervisor propaga el error y el router
cierra la WS del cliente con 4500. Reintentar adentro del wrapper escondería
fallas que el frontend tiene que manejar.

## 8. Supervisor (`streaming/supervisor.py`)

`LiveStreamSupervisor(modules, strike_sink).run(audio_iter)` corre la sesión.

Estructura:
- Tarea 1: consume `audio_iter` (proviene del WS del cliente, ver router) y
  reenvía cada chunk al wrapper Gemini.
- Tarea 2 (en background): itera `gemini.iter_tool_calls()`. Por cada call:
  1. Mapea `name` → categoría via `TOOL_NAME_TO_MODULE`. Si no matchea, ack y descarta.
  2. Filtro anti-alucinación: `transcript_snippet` debe tener ≥ 4 caracteres y
     `word` no vacío. Si falla, ack y descarta.
  3. Severity default a `"low"` si viene fuera del enum.
  4. Construye `StrikeEvent` y lo emite vía `strike_sink`.
  5. Ack siempre, incluso si dropeamos el strike.

`StrikeEvent` lleva: `category`, `word`, `transcript_snippet`, `severity`,
`received_at_ms`. El router lo serializa al WS del cliente.

El supervisor no escribe en BD. Es transporte + filtro.

## 9. Router (`presentation/routers/live_ws.py`)

`@router.websocket("/live/sessions/{session_id}/stream")` registrado bajo
`/api`. Auth: `authenticate_ws(token, db)` igual que `fluency.py`.

Flujo:
1. Accept WS.
2. Auth con token del query string.
3. Recibe start message (10s timeout). Valida `modules`.
4. `validate_parent_live_session(db, user, session_id)` para confirmar que el
   `session_id` apunta a una live activa del user.
5. Crea `asyncio.Queue` bounded (64 chunks ≈ 3s slack); drop oldest si se llena.
6. Spawnea `read_client()` task que copia bytes del WS al queue, hasta que
   llega `{"type": "end"}` o disconnect.
7. Manda `{"type": "ready"}`.
8. Corre `supervisor.run(audio_iter)` donde `audio_iter` consume el queue.
9. Cleanup: cancela el reader, manda `session_ended`, cierra WS.

Errores propagan a `4500 Internal error`. Disconnect del cliente cierra la
sesión Gemini limpio gracias al `async with` del wrapper.

## 10. Decisiones de diseño

- **Threshold 1 strike**: el rationale es pedagógico — si el modelo detecta un
  error real, el "corten" tiene que llegar inmediato para que el alumno asocie
  el error con su acción. El falso positivo es el riesgo conocido; lo
  amortizamos con el filtro `transcript_snippet` y `severity` explícita.

- **`transcript_snippet` como contrato anti-alucinación**: el modelo está
  obligado por el prompt a citar audio real. El supervisor descarta cualquier
  call sin snippet. Es la versión streaming del contrato `transcript` del
  composed eval anterior.

- **Sin persistencia de strikes**: los datos longitudinales viven en el
  composed eval que ya corría al cerrar la sesión. Persistir strikes
  duplicaría tablas y rompería la regla CLAUDE.md de "no campos free-text
  generados por LLM en BD" (los `transcript_snippet` y `suggestion` son
  exactamente eso).

- **Modelo: `gemini-3.1-flash-live-preview`**. La Developer API solo
  expone los modelos Live como preview; el GA real
  (`gemini-live-2.5-flash-native-audio`) existe solo en Vertex AI.
  Originalmente apuntamos a
  `gemini-2.5-flash-native-audio-preview-12-2025`, pero ese modelo
  expone un bug confirmado de Google: function calling provoca
  desconexiones `1011 internal error` mid-stream (python-genai issue
  #1832 y foro discuss.ai.google.dev sobre "Repeated 1011 Internal
  error" en preview-12-2025). 3.1-flash-live-preview soporta tool
  calling sincrónico (que es exactamente lo que el supervisor hace:
  ack por cada call antes de continuar) y es el modelo que Google
  recomienda para nuevas builds de voice agents. Cumple la regla
  CLAUDE.md de evitar `*-latest`. Para cambiar a un GA futuro basta
  con tocar `settings.gemini_live_model`.

- **Tools son declaraciones agnósticas del SDK**: `streaming/tools.py` exporta
  diccionarios, no objetos genai. El wrapper los convierte a
  `FunctionDeclaration` al abrir la WS. Esto permite testear sin importar el
  SDK y agregar nuevos módulos sin tocar la integración.

- **Modularidad para nuevos módulos**: agregar `pauses` o cualquier nuevo
  análisis = nueva entrada en `_TOOL_BY_MODULE` + nueva sección en
  `live_prompt.py`. El supervisor no cambia. El router no cambia. El frontend
  agrega la categoría en la unión TypeScript y un strike counter más.

- **Audio en PCM 16k mono**: la Live API espera `audio/pcm;rate=16000`. El
  frontend convierte el output del micrófono a este formato (Web Audio API)
  antes de mandarlo. No usamos webm/opus aquí porque el modelo Live evita el
  decoder y opera sobre PCM crudo.

## 11. Logging diagnóstico

Todas las capas del pipeline emiten `logger.info` con un prefijo
identificable para poder rastrear fallas sin habilitar debug:

| Prefijo | Origen |
|---|---|
| `[live-ws]` | Router WS: accept, auth, validación de modules/parent, ready, supervisor outcome, close |
| `[supervisor]` | Orquestador: start, audio iterator drained, strike emitido o descartado y motivo |
| `[live-gemini]` | Wrapper genai: open, close, errores, tool call recibido, contador de chunks enviados (1, 10, 100, 1000, ...) |

Una sesión saludable produce algo así en orden:

```
[live-ws] WS accepted for session_id=...
[live-ws] auth ok user_id=...
[live-ws] start ok modules=[...]
[live-ws] sent ready, starting supervisor
[supervisor] starting (modules=[...])
[live-gemini] opening Live WS (model=..., modules=[...])
[live-gemini] Live WS opened
[live-gemini] chunks sent: 1
[live-gemini] chunks sent: 10
[live-gemini] tool call received: name=flag_muletilla id=... args_keys=[...]
[supervisor] strike emitted category=muletillas word='este' severity=low
...
[supervisor] audio iterator drained, signaling end
[supervisor] finished
[live-gemini] closing Live WS
[live-gemini] Live WS closed
[live-ws] closing (supervisor_failed=False)
```

## 12. Pendientes

- Escalamiento: una WS por usuario simultáneo. Validar el límite de Cloud Run
  antes de subir a producción real.
- Tests del supervisor con un fake `LiveStreamGeminiSession` que emita tool
  calls sintéticos.
