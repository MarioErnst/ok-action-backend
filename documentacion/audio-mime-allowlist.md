# Audio MIME Allowlist — Validación de uploads de audio

## 1. Descripción funcional

Helper transversal que valida el `Content-Type` de los `UploadFile` recibidos en los endpoints que envían audio a Gemini. Reemplaza el patrón previo `mime_type = audio.content_type or "audio/webm"`, que aceptaba cualquier valor (incluso vacío) y producía 502 opacos cuando Gemini rechazaba el MIME real.

Antes del helper, si el navegador mandaba un `Content-Type` exótico (p.ej. `audio/aac` desde un Safari raro o `application/octet-stream` desde un dispositivo mal configurado), la sesión llegaba hasta Gemini, fallaba con un error genérico, y el frontend solo veía un 502.

## 2. Ubicación

`backend/app/infrastructure/audio/mime.py`.

Convive con `silence_detector.py` (misma carpeta) porque ambos son utilidades de la capa de audio, aunque el MIME es presentation-layer en uso. La función se importa desde los routers y se invoca al inicio del endpoint.

## 3. Lista de MIMEs aceptados

| MIME base | Origen típico |
|-----------|---------------|
| `audio/webm` | Chrome (desktop + Android), Edge |
| `audio/mp4` | iOS Safari (única opción soportada por MediaRecorder en iOS) |
| `audio/ogg` | Firefox |
| `audio/mpeg` | Tests / clientes que envíen MP3 |
| `audio/wav`, `audio/x-wav` | Tests / clientes que envíen WAV |

Los parámetros de codec (p.ej. `;codecs=opus`) se eliminan antes de chequear contra la lista. La función devuelve el MIME base normalizado, que es lo que Gemini espera en `types.Part.from_bytes(mime_type=...)`.

## 4. Contrato de la función

```python
def verify_audio_mime(audio: UploadFile) -> str
```

- Recibe el `UploadFile` directo del request.
- Devuelve el MIME base normalizado (lowercase, sin parámetros).
- Si el MIME está vacío o fuera de la allowlist, lanza `HTTPException(415, ...)`.

## 5. Endpoints donde aplica

| Router | Endpoint | Descripción |
|--------|----------|-------------|
| `accentuation.py` | `POST /accentuation/evaluate` | Evaluación por frase |
| `pronunciation.py` | `POST /pronunciation/evaluate` | Evaluación por frase |
| `muletillas.py` | `POST /muletillas/evaluate` | Evaluación de respuesta abierta |
| `precision.py` | `POST /precision/sessions/{id}/rounds` | Evaluación por ronda |
| `linguistic_versatility.py` | `POST /linguistic-versatility/sessions/{id}/rounds` | Evaluación por ronda |
| `live.py` | `POST /live/sessions/{id}/evaluate` | Evaluación compuesta multi-módulo |
| `live.py` | `POST /live/sessions/{id}/evaluate-frame` | Evaluación por frame |

## 6. Decisiones de diseño

- **Listado fijo (frozenset), no configuración por env**: el set de browsers soportados es estable y la lista funciona como contrato explícito. Si en el futuro hay que aceptar `audio/aac` o `audio/flac`, se agrega y se documenta acá.
- **`base = content_type.split(";", 1)[0]`**: codecs se descartan porque Gemini no los consume y porque mantenerlos haría imposible hacer matching exacto contra la allowlist.
- **`HTTP 415`** (Unsupported Media Type) en vez de 422: el 415 es semánticamente el status correcto para "no acepto este Content-Type". El frontend puede mostrar un mensaje distinto al del 422 (validación de payload).
- **Mensaje del error incluye el `Content-Type` recibido**: facilita el debugging cuando un device mande algo inesperado. No expone PII.
- **`verify_audio_mime(audio)` se llama antes de `audio.read()`**: evita leer bytes que vamos a tirar.

## 7. Cómo agregar el chequeo a un nuevo endpoint

```python
from app.infrastructure.audio.mime import verify_audio_mime

@router.post("/...")
async def my_endpoint(audio: UploadFile, ...):
    mime_type = verify_audio_mime(audio)
    audio_bytes = await audio.read()
    # pasar mime_type a Gemini
```

No requiere registrar nada en `main.py` ni agregar dependencias FastAPI: es una llamada directa.
