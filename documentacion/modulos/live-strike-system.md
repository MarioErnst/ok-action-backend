# Sistema de Strikes en Sesión Live — Backend

A partir de la branch `feature/live_assemblyai_muletillas` (mayo 2026), el
strike system de la sesión live se basa en transcripción literal con
**AssemblyAI Universal-3 Pro Streaming** (`u3-rt-pro`) más un matcher contra
diccionario de muletillas en español. El supervisor consume final transcripts,
busca tokens del diccionario y emite **un strike por cada muletilla detectada**.
El umbral en el frontend sigue siendo **1 strike = corten inmediato**.

Este archivo cubre solo los cambios backend; el lado frontend vive con el mismo
nombre en `ok-action-frontend/documentacion/modulos/live-strike-system.md`.

## 1. Por qué AssemblyAI reemplazó a Gemini Live

| Aspecto | Gemini Live + function tools | AssemblyAI Universal-3 Pro Streaming |
|---|---|---|
| Naturaleza del modelo | Generativo conversacional | Transcriptor verbatim |
| Forma de detección | Tool calls predichos del audio | Tokens en el transcript matcheados contra diccionario |
| Riesgo de alucinación | Alto — completa patrones esperados | Nulo — solo reporta lo escuchado |
| Latencia | 2-3 s por pulse forzado | 1-2 s por turn final natural |
| Idioma | Español aceptable | Español nativo, prompt `Transcribe Spanish (Latin American) verbatim` |
| Costo aprox / hora | ~$0.45 / hora de WS | ~$0.45 / hora de WS |

El intento previo con Gemini Live (en `feature/live_corten`) confirmó por
experiencia que el modelo inventaba muletillas para "satisfacer" turnos forzados
de actividad. AssemblyAI elimina esa clase entera de falso positivo a cambio de
perder la capacidad de detectar errores de pronunciación/acentuación en vivo —
que se mueven al composed-eval del cierre.

## 2. Alcance actual del strike system live

| Módulo | Detección live | Auto-stop | Detección al cierre |
|---|---|---|---|
| `muletillas` | AssemblyAI + dictionary matcher | 1er strike (corte inmediato) | Persiste hija con métricas |
| `facial_expression` | MediaPipe client-side (`useEmotionStop`) | 5s emoción negativa sostenida | Payload `facial_summary` |
| `phonation` | AudioWorklet client-side (pitch / dB) | 5 breaks de pitch en ventana de 10s | Payload `phonation_summary` |
| `loudness` | AudioWorklet client-side + classifier de banda | 3s continuos en banda `clipping` | Payload `loudness_summary` |

`pronunciation` y `accentuation` fueron retirados del set componible de live a
favor de phonation/loudness; sus módulos standalone siguen funcionando en sus
páginas dedicadas.

### Stop reasons

`StopReasonEnum` en BD expone los siguientes valores activos:
- `user_stop`, `time_limit`, `error`, `completed` — históricos.
- `auto_stop_strikes` — corte por muletilla detectada en vivo.
- `auto_stop_emotion` — corte por emoción negativa sostenida.
- `auto_stop_loudness` — corte por clipping continuo 3s (migración 0009).
- `auto_stop_phonation` — corte por 5 breaks de pitch en 10s (migración 0009).

## 3. Estructura de directorios

```
app/use_cases/live/
├── sessions.py                    ← lifecycle existente
├── composed/                      ← intacto, sigue evaluando pron/acc al cierre
└── streaming/
    ├── __init__.py
    ├── muletillas_dictionary.py   ← NUEVO: unigrams + bigrams + extract_muletillas()
    └── supervisor.py              ← REEMPLAZADO: ahora consume transcripts de AssemblyAI

app/infrastructure/ai/
├── composed_live_gemini.py        ← intacto (composed-eval)
└── live_stream_assemblyai.py      ← NUEVO: wrapper async del SDK assemblyai.streaming.v3

app/presentation/routers/
├── live.py                        ← intacto (lifecycle HTTP + composed-eval)
└── live_ws.py                     ← intacto (mismo protocolo WS hacia el cliente)
```

**Archivos eliminados** (vivían en `feature/live_corten` y desaparecen en esta
branch): `infrastructure/ai/live_stream_gemini.py`,
`use_cases/live/streaming/tools.py`, `use_cases/live/streaming/live_prompt.py`,
y el setting `gemini_live_model` en `config.py`.

## 4. Protocolo WebSocket cliente↔backend

Sin cambios. Es el mismo contrato que el supervisor anterior:

```
client -> server: {"type": "start", "modules": ["muletillas"]}
server -> client: {"type": "ready"}
client -> server: <bytes>                            # PCM16 16 kHz mono
client -> server: {"type": "end"}
server -> client: {"type": "strike", "category": "muletillas",
                    "word": "este", "transcript_snippet": "ahora este es",
                    "severity": "low", "received_at_ms": 1737000123456}
server -> client: {"type": "session_ended"}
server: cierra WS
```

El backend hoy solo emite `category=muletillas`. La narrowing del union en
frontend asegura que cualquier consumidor sepa que un strike WS es siempre una
muletilla.

## 5. Diccionario de muletillas (`muletillas_dictionary.py`)

- `SPANISH_FILLER_UNIGRAMS`: conjunto de tokens lowercase que siempre cuentan
  (`eh`, `ehh`, `este`, `esto`, `esta`, `mmm`, `ah`, `viste`, `tipo`, `pues`,
  `digamos`, etc.).
- `SPANISH_FILLER_BIGRAMS`: pares consecutivos (`("o", "sea")`, `("o", "sé")`).
- `extract_muletillas(transcript) -> list[MuletillaMatch]`: tokeniza con regex
  Unicode, prioriza bigrams sobre unigrams cuando se solapan, devuelve cada
  occurrence con `word`, `start_char`, `end_char` y `context_snippet`.

La lista es deliberadamente conservadora. Se editan los conjuntos cuando los
logs muestren falsos positivos o pérdidas reales en sesiones de prueba.

## 6. Wrapper AssemblyAI (`infrastructure/ai/live_stream_assemblyai.py`)

Envuelve el SDK síncrono `assemblyai.streaming.v3.StreamingClient` con dos
patrones:
- `asyncio.to_thread(...)` para no bloquear el event loop en `connect`, `stream`
  y `disconnect`.
- `asyncio.Queue` + `loop.call_soon_threadsafe(...)` para marshallear los
  callbacks (que llegan en threads del SDK) al supervisor async.

Configuración de la sesión (`StreamingParameters`):
- `speech_model="u3-rt-pro"` (Universal-3 Pro Streaming).
- `sample_rate=16000`.
- `prompt=...` corto, en inglés, pidiendo verbatim español-latam + lista de
  muletillas a preservar.
- `keyterms_prompt=[...]` con las muletillas como boost de keyterms.

El wrapper solo expone `iter_final_transcripts()` para el supervisor; los
partials se ignoran porque AssemblyAI corrige el partial conforme gana
contexto y dispararíamos strikes que después se "borraban".

**Cierre crítico**: `aclose()` siempre llama `disconnect(terminate=True)` para
emitir el mensaje `Terminate`. Una sesión abandonada sigue facturando hasta el
cap de 3 horas de AssemblyAI; el `async with` del `open()` garantiza el cierre
limpio aunque haya excepciones.

## 7. Supervisor (`use_cases/live/streaming/supervisor.py`)

`LiveStreamSupervisor(modules=["muletillas"], strike_sink).run(audio_iter)`.

Estructura simplificada respecto a la versión con Gemini Live:
- Tarea principal: consume `audio_iter` y reenvía cada chunk PCM al wrapper.
- Tarea de fondo: itera `iter_final_transcripts()`, corre el matcher y emite
  `StrikeEvent` por cada match.
- No hay pulser, no hay VAD propio, no hay filtros de severidad ni de snippet.
  AssemblyAI ya hace el trabajo de detectar speech y formatear turns.

`StrikeEvent` queda como dataclass con `category`, `word`, `transcript_snippet`,
`severity` (siempre `"low"` por ahora) y `received_at_ms`. El sink del router
serializa este event como JSON al cliente sin cambios.

## 8. Logging diagnóstico

Mantiene los prefijos previos:

| Prefijo | Origen |
|---|---|
| `[live-ws]` | Router WS: accept, auth, validación de modules/parent, ready, supervisor outcome, close |
| `[supervisor]` | Orquestador: start, audio iterator drained, strike emitido, contadores |
| `[live-assemblyai]` | Wrapper SDK: open, close, transcripts finales, errors |

Sesión saludable:

```
[live-ws] WS accepted for session_id=...
[live-ws] auth ok user_id=...
[live-ws] start ok modules=['muletillas']
[live-ws] sent ready, starting supervisor
[supervisor] starting (modules=['muletillas'])
[live-assemblyai] opening Streaming WS (model=u3-rt-pro, sample_rate=16000)
[live-assemblyai] Streaming WS opened
[supervisor] receive loop started
[supervisor] forwarded 1 chunks / 9600 bytes from client
[live-assemblyai] turn final: 'ahora vamos a probar el sistema'
[live-assemblyai] turn final: 'eh este es un ejemplo'
[supervisor] STRIKE category=muletillas word='eh' snippet='eh este es un ejemplo'
[supervisor] STRIKE category=muletillas word='este' snippet='eh este es un ejemplo'
[supervisor] audio iterator drained after 220 chunks / 704000 bytes
[live-assemblyai] closing Streaming WS
[live-assemblyai] Streaming WS closed
[live-ws] closing (supervisor_failed=False)
```

## 9. Variable de entorno

Nueva variable obligatoria:

```env
ASSEMBLYAI_API_KEY=...   # cargada por config.Settings.assemblyai_api_key
```

`backend/.env` está en `.gitignore`. El valor real nunca se commitea.

## 10. Decisiones de diseño

- **Solo finals, no partials**: confiabilidad sobre velocidad marginal. Un
  partial puede mutar mientras la frase avanza; un strike disparado por
  partial podría corregirse en la siguiente actualización y dejar al usuario
  cortado por nada.
- **Diccionario en backend, no STT-side**: AssemblyAI no filtra muletillas
  por idioma (su parámetro `filler_words` es solo inglés). Hacemos el filtro
  acá con un conjunto que es trivialmente editable cuando aparecen casos
  reales.
- **Severidad fija `"low"`**: el matcher no tiene base para distinguir
  severidad sin contexto histórico. El campo queda en el wire format por
  compatibilidad con el frontend y para permitir lógica futura (ej. subir a
  `medium` si la misma muletilla se repite N veces).
- **Pron/acc fuera del live**: aceptamos perder corten en vivo para esos
  módulos a cambio de la confiabilidad del composed-eval al cierre.

## 11. Pendientes

- Tests del matcher con casos negativos (palabras del diccionario en contexto
  no-filler).
- Métrica de falsos positivos en sesiones reales para ajustar el diccionario.
- Estimar costo real por sesión (AssemblyAI Universal-3 Pro Streaming = $0.45
  / hora) y dimensionar el free tier ($50 → ~111 horas).
