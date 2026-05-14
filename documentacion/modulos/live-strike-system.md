# Sistema de Strikes en Sesión Live — Backend

Rediseño del flujo de Sesión Live que agrega evaluación por frames durante la sesión (no solo al cierre), reemplaza el módulo `consistency` por `facial_expression` en la composición, y extiende `StopReasonEnum` con dos nuevos motivos de corte automático.

La feature comparte nombre con la documentación frontend (`live-strike-system.md`). Este archivo cubre solo los cambios backend.

## 1. Cambios funcionales en backend

| Aspecto | Antes | Después |
|---|---|---|
| Módulos componibles en live | muletillas, accentuation, pronunciation, **consistency** | muletillas, accentuation, pronunciation, **facial_expression** |
| Evaluación durante grabación | No existía | Endpoint nuevo `POST /api/live/{id}/evaluate-frame` que recibe blobs de 5–8s y devuelve detecciones para alimentar el strike system del cliente |
| Stop reasons | `user_stop`, `time_limit`, `error`, `completed` | + `auto_stop_strikes`, `auto_stop_emotion` |
| Pipeline Gemini | Una sola llamada al cierre (composed) | Dos pipelines: streaming (por frame, lightweight) + composed (al cierre, igual que hoy pero con sección facial en lugar de consistency) |

## 2. Cambios en BD

### Migración nueva: extender `stop_reason_enum`

Postgres ENUM nativo. Migración Alembic que agrega los dos valores:

```sql
ALTER TYPE stop_reason_enum ADD VALUE 'auto_stop_strikes';
ALTER TYPE stop_reason_enum ADD VALUE 'auto_stop_emotion';
```

Importante: `ALTER TYPE ... ADD VALUE` no es transaccional en versiones viejas de Postgres y no se puede correr dentro del mismo `BEGIN` que tiene otras DDL. La migración debe quedar **sola**, en una revisión propia, con `op.execute("COMMIT")` antes del `ADD VALUE` si es necesario (probar antes de aplicar a Cloud SQL).

### Sin tablas nuevas

Los frames evaluados durante la sesión no se persisten. Son ephemeral: cliente los manda, backend los pasa por Gemini, devuelve la respuesta, cliente decide strikes. El score final por módulo sigue saliendo del composed final sobre el audio completo (lógica intacta de `app/use_cases/live/composed/persist.py`).

## 3. Estructura de directorios

```
app/use_cases/live/
├── sessions.py                ← lifecycle existente (start, finalize, abandon)
├── composed/                  ← evaluación final (existente)
│   ├── prompts.py             ← actualizo: consistencia fuera, expresión facial dentro
│   ├── schemas.py             ← actualizo: idem
│   └── persist.py             ← actualizo: idem
└── streaming/                 ← NUEVO, evaluación por frame
    ├── __init__.py
    ├── prompts.py             ← prompt de frame con "evalúa hasta última oración completa"
    └── schemas.py             ← schema reducido orientado a strikes
                               
app/infrastructure/ai/
├── composed_live_gemini.py    ← actualizo: schema con facial en lugar de consistency
└── live_frame_gemini.py       ← NUEVO, cliente Gemini para frames

app/presentation/
├── routers/
│   └── live.py                ← actualizo: agrego endpoint evaluate-frame
└── schemas/
    └── live.py                ← actualizo: schemas de request/response de frame
```

## 4. Pipeline de frames

### 4.1 Endpoint nuevo

`POST /api/live/{session_id}/evaluate-frame`

| Campo | Tipo | Descripción |
|---|---|---|
| `frame_index` | int (form-data) | Correlativo desde 0. |
| `evaluated_so_far_seconds` | int (form-data) | Segundos transcurridos en la sesión al inicio del frame, para que Gemini sepa el contexto. |
| `modules` | list[str] (form-data, repetido) | Subset de `{muletillas, accentuation, pronunciation}`. Expresión facial NO se evalúa por frame en backend (se hace 100% en cliente). |
| `audio` | file (multipart) | Blob del frame (incluye 500ms de overlap con el frame anterior si `frame_index > 0`). |

Respuesta JSON (ver `streaming/schemas.py`):

```json
{
  "frame_index": 7,
  "evaluated_until_seconds": 4.2,
  "muletillas": {
    "total": 2,
    "detected": [
      {"word": "este", "count": 1, "severity": "low", "timestamp_ms": 1200},
      {"word": "o sea", "count": 1, "severity": "low", "timestamp_ms": 2800}
    ]
  },
  "accentuation": {
    "pronunciation_score": 62,
    "rhythm_score": 48,
    "intonation_score": 55,
    "stress_score": 60
  },
  "pronunciation": {
    "vowel_score": 70,
    "consonant_score": 58,
    "fluency_score": 65,
    "intelligibility_score": 75
  }
}
```

Solo aparecen las secciones de los módulos pedidos. `evaluated_until_seconds` indica el segundo del frame hasta el que Gemini consideró evaluable (la última oración completa). El cliente usa ese valor para no contar dos veces lo que tape el overlap del frame siguiente, aunque en la práctica el overlap es generoso y la suma de errores entre frames se trata como independiente.

### 4.2 Prompt de frame (`streaming/prompts.py`)

Características distintivas respecto al composed:

- Incluye explícitamente: "Este audio es un FRAGMENTO de una sesión más larga que está en curso. El estudiante sigue hablando después del corte."
- "Evalúa solo hasta la última oración completa que escuches. Reporta esa duración en `evaluated_until_seconds`."
- "No asignes scores 0 si el fragmento es corto: usa 50 como neutral, no como castigo."
- Sin gate de audio inaudible tan estricto: si el frame es muy corto o ruidoso, devuelve scores 50 y `detected: []` para muletillas en lugar de fallar.

Como el composed, organiza secciones por módulo: muletillas / accentuation / pronunciation. **No incluye facial_expression** (eso se evalúa solo en cliente).

### 4.3 Cliente Gemini (`live_frame_gemini.py`)

Espejo de `composed_live_gemini.py` pero pinneado al mismo modelo (hoy `gemini-2.5-flash` per regla de no usar `*-latest`). Diferencias:

- Schema más chico (sin `feedback` strings — el cliente no los muestra durante la sesión).
- Timeout más corto (5 segundos vs 30 del composed) — si Gemini tarda más, mejor descartar el frame que congelar la cadena.
- Sin retry. La pérdida de un frame es aceptable; el strike system es tolerante.

## 5. Cambios en composed (evaluación final)

### 5.1 Reemplazo `consistency` → `facial_expression`

`ComposableModule` literal en `composed/prompts.py` pasa de:

```py
ComposableModule = Literal["muletillas", "accentuation", "pronunciation", "consistency"]
```

a:

```py
ComposableModule = Literal["muletillas", "accentuation", "pronunciation", "facial_expression"]
```

`VALID_MODULES` igual.

`_CONSISTENCY_SECTION` se borra del prompt. Se agrega `_FACIAL_EXPRESSION_SECTION` con la consigna de evaluar emociones a partir del **video** del frame en su totalidad. Pero ojo: el composed actual evalúa **audio puro**, no video. Para incluir expresión facial en el composed final hay dos opciones:

- **A**: el composed sigue siendo solo audio y la sección facial se evalúa en cliente sobre el agregado de las predicciones de los 15fps. Score final por módulo facial = % de tiempo en cada emoción durante la sesión, persistido directamente en `facial_expression_metrics`.
- **B**: el frontend manda video al endpoint composed final. Gemini multimodal evalúa frames del video además del audio.

**Decisión**: opción **A** por ahora (más simple, no requiere subir video al backend, mismo costo Gemini que hoy). El composed prompt se actualiza para incluir `facial_expression` solo conceptualmente, pero el backend persiste `facial_expression_metrics` desde un payload que el frontend manda en el body del `finalize-session` (agrega un nuevo campo `facial_summary` opcional).

### 5.2 Persistencia (`composed/persist.py`)

Cuando `facial_expression` está en `modules`, el `composed/persist.py` lee el payload `facial_summary` (en lugar de la respuesta Gemini) y crea la fila en `facial_expression_metrics`:

```py
facial_expression_metrics(
    session_id=child_session_id,
    expressiveness_score=...,
    top_emotion=...,
    happy_pct=...,
    sad_pct=...,
    angry_pct=...,
    surprised_pct=...,
    fearful_pct=...,
    disgusted_pct=...,
    neutral_pct=...,
)
```

Los 7 porcentajes deben sumar 100 (regla del schema). El frontend los calcula desde el stream del clasificador y los manda al backend.

## 6. Endpoint `finalize-session`

`POST /api/live/{session_id}/finalize` ya existe. Cambios:

- Acepta opcionalmente `facial_summary` en el body si `facial_expression` está entre los módulos componibles seleccionados.
- Si el cliente pasa `stop_reason` (campo opcional nuevo), se acepta solo si está en `{auto_stop_strikes, auto_stop_emotion}` y el endpoint registra ese motivo en `live_metrics`. En caso contrario, default `completed`.
- Si `stop_reason` indica auto-stop, el `status` del padre se marca `aborted` (no `completed`).

Alternativa: usar el endpoint `abandon` existente con los nuevos `stop_reason`. Hacer eso requiere que el cliente decida llamar `finalize` o `abandon` según el caso. Decisión: **mantener `finalize` para todos los caminos** y agregar `stop_reason` opcional, así el cliente no se complica con dos endpoints. `abandon` queda solo para el escenario "el usuario cerró el tab" (best-effort fire-and-forget como hoy).

## 7. Validaciones y errores

- `evaluate-frame` valida que la sesión padre exista, esté `active`, y pertenezca al usuario autenticado. Si no, 404 / 403.
- Si `modules` incluye módulos no válidos (ej. `consistency`, ya removido), 400.
- Si el audio del frame está corrupto o tiene MIME inválido, 415.
- Errores de Gemini se traducen a 502 (gateway). El cliente sabe que un 502 = descartar este frame y seguir.

## 8. Performance

- Una sesión de 5 min produce ~60 calls a `evaluate-frame`. Multiplica el costo Gemini por 60. Validar contra quotas del proyecto antes de habilitar en producción.
- Cloud Run autoscale: cada call lleva ~1.5–3s. Con concurrencia default (`max=80`) basta para varios usuarios simultáneos. Sin cambios de config.
- Gemini Flash en `southamerica-west1`: probar rate limit; si se acerca, fallback a `us-central1` (con latencia agregada).

## 9. Decisiones de diseño justificadas

- **`evaluate-frame` no persiste nada**: cada call es read-only respecto a BD (solo lee la sesión para validar). Los resultados van en la respuesta y el cliente los consume. Esto simplifica el endpoint a "proxy a Gemini con validación de auth".
- **`streaming/` separado de `composed/`**: la lógica de framing es muy distinta (prompts más cortos, schema reducido, timeout chico, no retry). Mezclarla con composed comprometería ambos. Atomic design + clean architecture: cada use case con su propia carpeta.
- **`facial_expression` se evalúa solo en cliente**: subir video al backend para que Gemini lo procese duplicaría el costo y aumentaría latencia. El clasificador ML actual del módulo standalone (MediaPipe FaceLandmarker + clasificador propio) es bueno suficientemente para esto.
- **`finalize` acepta `stop_reason` opcional vs endpoint nuevo**: agregar otro endpoint era duplicación. Un solo endpoint que acepta más casos respeta single responsibility (cerrar la sesión) y simplifica el cliente.
- **`auto_stop_strikes` y `auto_stop_emotion` separados**: granularidad para análisis posterior. ¿Cuántas sesiones cortadas por emociones vs por errores audio? Un solo enum genérico perdería esa info.
- **Sin retry en frame Gemini**: si un frame se pierde, el strike no se cuenta — error de tipo II (falso negativo). Es preferible a congelar el pipeline. La cadena entera se recupera al siguiente frame.

## 10. Pendientes que no resuelve este doc

- Tabla `live_frame_evaluations` para trazabilidad longitudinal (no para esta versión).
- Endpoint para re-evaluar una sesión cortada (no para esta versión).
- Configurabilidad del umbral 55 vía endpoint (no para esta versión, constante en código).

## 11. Hotfix de grounding en la evaluación compuesta

A partir del hotfix `live-evaluation-grounding`, el prompt y el schema del composed
contra Gemini incorporan un mecanismo de anti-alucinación:

### Campo `transcript` en la raíz del JSON

Cuando se solicita al menos un módulo evaluable por audio (`muletillas`,
`accentuation`, `pronunciation`), el schema requiere un campo `transcript` en la
raíz con la transcripción literal del audio. La prompt obliga a transcribir
**antes** de evaluar y declara que cualquier item anclado (muletilla, error
fonémico, error prosódico) que el modelo reporte debe corresponder a una palabra
o segmento del propio `transcript`. Si la palabra no aparece, no puede listarla.

### Items anclados por módulo (efímeros, no persistidos)

| Módulo | Campo nuevo | Forma |
|---|---|---|
| `muletillas` | `muletillas_positions[]` | `{word, start_char, end_char}` con la contraintegridad `transcript[start_char:end_char] == word`. Una entrada por ocurrencia. |
| `accentuation` | `prosodic_errors[]` | `{word, expected_stress, actual_issue, suggestion}`; `word` debe aparecer en `transcript`. |
| `pronunciation` | `phoneme_errors[]` | `{phoneme, word, actual_issue, suggestion}`; `word` debe aparecer en `transcript`. |

Todos estos campos son **efímeros**: viajan en la respuesta HTTP para que el
frontend renderice retroalimentación accionable y como contrato anti-alucinación
para el LLM. **No se persisten en BD** — las tablas `<modulo>_metrics` no tienen
columnas para texto generado por LLM (regla CLAUDE.md backend). `persist.py`
ignora estos campos al guardar.

### `temperature=0.2` en la llamada Gemini

`composed_live_gemini.py` y los tres servicios standalone (`muletillas_gemini.py`,
`pronunciation_gemini.py`, `gemini.py` de acentuación) ahora setean
`temperature=0.2` en `GenerateContentConfig`. Reduce la varianza de las tareas de
detección y clasificación (listas de muletillas, errores) manteniendo naturalidad
en el campo `feedback`.

### Por qué este hotfix

- **Antes**: Gemini reportaba muletillas que no estaban en el audio (sesgo del
  prompt que listaba ejemplos típicos como "la verdad", "de hecho"). La
  pronunciación devolvía solo scores agregados sin errores accionables. La
  acentuación, idem.
- **Ahora**: el transcript es contrato. Los listados de muletillas, errores
  fonémicos y errores prosódicos están anclados a palabras del transcript. El
  frontend puede mostrar al usuario qué se transcribió y dónde estuvieron los
  errores, permitiéndole verificar contra el audio real.

## 12. Hotfix de grounding en la evaluación por frame

La sección 11 explica el cambio en el composed (cierre de sesión). Esta sección
documenta el cambio paralelo en el flujo por frame (durante la sesión), que es
el que alimenta el strike counter.

### 12.1 Frame Gemini con `temperature=0.2`

`live_frame_gemini.py` ahora setea `temperature=0.2` en `GenerateContentConfig`.
Lo mismo que en el composed: el frame es una tarea de detección/clasificación,
y la variabilidad en defaults rompe la estabilidad del strike counter (un mismo
audio podía sumar 1 strike en una corrida y 0 en la siguiente).

### 12.2 Campos nuevos en el schema del frame

| Campo | Ubicación | Forma |
|---|---|---|
| `transcript` | raíz del JSON | string. Requerido cuando hay al menos un módulo seleccionado. |
| `muletillas.muletillas_positions[]` | sección muletillas | `{word, start_char, end_char}`, una entrada por ocurrencia, ancladas a `transcript`. |
| `accentuation.prosodic_errors[]` | sección acentuación | `{word, expected_stress, actual_issue, suggestion}`. `word` debe aparecer literalmente en `transcript`. |
| `pronunciation.phoneme_errors[]` | sección pronunciación | `{phoneme, word, actual_issue, suggestion}`. `word` debe aparecer literalmente en `transcript`. |

Todos efímeros: viajan en la respuesta HTTP del frame y no se persisten (las
filas de frame jamás se persisten en BD, regla del módulo).

### 12.3 Anti-alucinación

Mismo contrato que el composed: el prompt obliga a transcribir antes de
evaluar y declara que cualquier `word` reportada como error debe aparecer
literalmente en el `transcript` del frame. El listado de ejemplos de
muletillas se redujo a `eh`, `este`, `o sea` con instrucción explícita de no
reportar las demás clásicas salvo que estén textualmente en el transcript.

### 12.4 Contrato de strike basado en items (no-dedup, threshold 2)

Importante: el strike counter del frontend cambia de "score parcial bajo" a
"items de error reportados por Gemini". El backend no calcula strikes —los
calcula `useFrameStrikes.ts` en el frontend— pero el schema del frame está
diseñado para soportar este flujo:

- **Muletillas**: cada ocurrencia (suma de `muletillas.detected[].count`)
  suma al counter. Threshold 2 → stop.
- **Pronunciación**: cada item en `pronunciation.phoneme_errors[]` suma 1
  al counter. Sin deduplicación: si Gemini reporta la misma palabra mal
  pronunciada en frames distintos, cada item cuenta. Threshold 2 → stop.
- **Acentuación**: cada item en `accentuation.prosodic_errors[]` suma 1
  al counter. Mismo no-dedup. Threshold 2 → stop.

Los tres contadores son **independientes**: cualquiera que llegue a 2
dispara el corte. 1 muletilla + 1 error de pronunciación NO detiene.

Los sub-scores (`vowel_score`, `pronunciation_score`, etc.) **siguen llegando**
en la respuesta y se promedian al cierre; lo que cambió es solo el disparador
del strike counter. La pantalla de feedback de strike también pasa a renderizar
palabra + detalle accionable en lugar del string genérico
`Score parcial mínimo: X`.

#### Por qué no-dedup

Una variante intermedia (dedup por palabra normalizada con threshold 3) se
implementó primero pero quedó demasiado permisiva: un usuario que repetía
6 veces el mismo error fonémico solo acumulaba 1 strike. El no-dedup con
threshold 2 da un solo "aviso" antes del corte, lo que en la práctica
refleja mejor la intención pedagógica del strike system. Gemini ya tiende
a agrupar errores repetidos del mismo fonema en una sola entrada de
`phoneme_errors[]` cuando ocurren en un mismo frame, así que el counter
no se dispara de forma absurda; sí se dispara cuando el error persiste
entre frames distintos.

### 12.5 Saltar Gemini cuando solo se selecciona facial_expression

`AUDIO_COMPOSABLE_MODULES` (alias público de `_GEMINI_EVALUATED_MODULES` en
`composed/prompts.py`) lista los módulos que dependen del modelo de audio:
`muletillas`, `accentuation`, `pronunciation`. El endpoint
`POST /live/sessions/{id}/audio-evaluation` ahora hace un short-circuit:

- Si la selección contiene al menos uno de esos módulos: lee el audio,
  valida el MIME y llama a Gemini igual que antes.
- Si la selección es **solo `facial_expression`**: salta la lectura del
  audio, salta la llamada a Gemini, y construye una respuesta sintética
  `{"audio_intelligible": True}`. `persist_composed_evaluation` ignora las
  secciones audio y solo persiste `facial_expression_metrics` a partir
  del `facial_summary` recibido en el body.

Beneficios:
- Cero tokens Gemini consumidos cuando el usuario practica solo expresión.
- Latencia del cierre de sesión cae de ~3-15s (llamada Gemini) a <100ms.
- Backend no exige que el audio sea inteligible (ni siquiera que tenga
  contenido) cuando no se va a evaluar.
