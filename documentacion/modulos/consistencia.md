# Consistencia - Documentacion Backend

## 1. Descripcion funcional

El modulo de Consistencia evalua si el desempeno oral del usuario se mantiene estable durante una intervencion completa. No busca medir solo si la respuesta es correcta, sino si el hablante sostiene una calidad pareja entre inicio, desarrollo y cierre.

El modulo analiza seis dimensiones:

- ritmo estable;
- volumen estable;
- claridad estable;
- foco en la consigna;
- seguridad al hablar;
- estructura de inicio, medio y cierre.

La evaluacion standalone se realiza al finalizar el intento porque la consistencia requiere comparar tramos de la misma intervencion. En sesion libre existe una integracion opcional como dimension `consistency`, evaluada en ciclos de 5 segundos.

## 2. Capas del modulo

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Router | `app/presentation/routers/consistency.py` | Expone el WebSocket `/consistency/session`, autentica al usuario y coordina captura, cierre y analisis final. |
| Use case | `app/use_cases/consistency/prompt_builder.py` | Construye el prompt de evaluacion para Gemini. |
| Use case | `app/use_cases/consistency/session_manager.py` | Mantiene estado en memoria, fallback sin audio y reglas de advertencia. |
| AI service | `app/infrastructure/ai/consistency_gemini.py` | Envia audio PCM a Gemini y valida el JSON esperado. |
| Live session | `app/use_cases/live_session/prompt_builder.py` y `app/infrastructure/ai/live_gemini.py` | Agrega la dimension `consistency` al analisis continuo de sesion libre. |

## 3. Modelo de datos

El modulo standalone no agrega tablas nuevas. La sesion de Consistencia corre por WebSocket y devuelve el resultado final al cliente.

En sesion libre, los resultados de `consistency` se guardan dentro de `live_sessions.analyses`, igual que las dimensiones `pron`, `acc` y `mul`.

Ejemplo parcial:

```json
{
  "dims": {
    "consistency": {
      "sc": 82,
      "classification": "mostly_consistent",
      "rhythm": 80,
      "volume": 90,
      "clarity": 84,
      "focus": 78,
      "confidence": 76,
      "structure": 82,
      "note": "Mantiene una linea clara con leve perdida de fuerza al cierre.",
      "det": []
    }
  }
}
```

## 4. Esquemas de solicitud y respuesta

### WebSocket standalone

Conexion:

```text
ws://<host>/consistency/session?token=<JWT>
```

Mensaje inicial:

```json
{
  "type": "start",
  "prompt_text": "Explica una propuesta de mejora para tu equipo."
}
```

Resultado:

```json
{
  "type": "analysis",
  "data": {
    "audio_intelligible": true,
    "score": 84,
    "rhythm_consistency_score": 82,
    "volume_consistency_score": 90,
    "clarity_consistency_score": 86,
    "focus_consistency_score": 80,
    "confidence_consistency_score": 78,
    "structure_consistency_score": 84,
    "classification": "mostly_consistent",
    "timeline": [
      { "segment": "inicio", "stability": 86, "rhythm": 84, "volume": 90, "clarity": 88, "focus": 82, "confidence": 84, "structure": 80, "note": "Inicio claro." }
    ],
    "volatility_events": [],
    "strengths": ["Mantiene volumen claro"],
    "improvement_areas": ["Cierra con mayor decision"],
    "recommendation": "Define una frase de cierre antes de grabar.",
    "fb": "Tu discurso se mantiene estable, con una leve baja de seguridad al final."
  }
}
```

## 5. Casos de uso

### `build_consistency_prompt(prompt_text)`

Normaliza la consigna y construye instrucciones para Gemini. El prompt obliga a verificar silencio, audio ininteligible, respuesta fuera de consigna y respuesta demasiado corta antes de puntuar.

### `ConsistencySessionState`

Mantiene el estado temporal de la conexion WebSocket. Define el limite de 120 segundos, guarda el analisis final y calcula advertencias:

- `audio_not_intelligible`;
- `low_consistency_score`;
- `consistency_breaks_detected`;
- `analysis_unavailable`.

### `build_no_audio_analysis()`

Genera un resultado local cuando el audio recibido es demasiado corto para enviarlo a Gemini.

## 6. Integracion con Gemini AI

**Archivo:** `app/infrastructure/ai/consistency_gemini.py`

**Modelo:** `gemini-2.5-flash`

Gemini recibe audio PCM 16 kHz junto con el prompt construido por el caso de uso. La respuesta se fuerza a JSON mediante `response_schema`.

La respuesta no incluye transcripcion. Esto evita mostrar texto inventado cuando el audio no permite reconocer frases exactas. Las observaciones deben describir estabilidad por tramo, no citar contenido literal.

## 7. Endpoints de la API

### WebSocket `/consistency/session`

- **Autenticacion:** JWT en query param `token`.
- **Entrada:** frames binarios PCM 16-bit, 16 kHz, mono.
- **Mensajes cliente:** `start`, `end`.
- **Mensajes servidor:** `ready`, `analysis`, `warning`, `session_ended`, `error`.
- **Cierre automatico:** 120 segundos.

### Integracion con `/live/session`

La dimension `consistency` se puede enviar dentro de `dims`:

```json
{
  "type": "start",
  "dims": ["pron", "consistency"]
}
```

Si no se selecciona, no altera el flujo de sesion libre. Si se selecciona, el backend incluye `dims.consistency` en cada ciclo de analisis.
