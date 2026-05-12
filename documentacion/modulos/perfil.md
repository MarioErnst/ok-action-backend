# Módulo de Perfil

Endpoints que sirven al panel personal del usuario (avance histórico y series de tiempo para los gráficos del dashboard).

Router: `app/presentation/routers/profile.py`, montado en `/api/profile`.

## GET `/api/profile/history`

Resumen agregado por módulo (no temporal). Devuelve, para cada módulo, el `averageScore` del usuario, un set de ejercicios sugeridos y la marca `viewed` para indicar si ya practicó. Este endpoint es el que alimenta hoy la vista de perfil "Mis avances".

**Autenticación**: requiere JWT (`Depends(get_current_user)`).

## GET `/api/profile/timeline`

Series temporales de actividad del usuario para los dos gráficos del dashboard (rendimiento y dedicación diaria).

**Autenticación**: requiere JWT.

**Query params**

| Param | Tipo | Default | Valores | Descripción |
|---|---|---|---|---|
| `range` | string | `30d` | `7d` \| `30d` \| `90d` \| `all` | Ventana temporal hacia atrás desde "ahora" (UTC). `all` no aplica filtro. |
| `module` | string | `all` | `all` o un valor de `ModuleEnum` (ej. `phonation`, `linguistic_versatility`) | Si es distinto de `all`, agrega solo las sesiones de ese módulo. Un valor inválido devuelve una respuesta vacía (no 500). |

**Lógica de agregación**

Bajo el capó, `app.use_cases.profile.timeline.get_user_timeline` ejecuta una sola query:

```sql
SELECT
  DATE(started_at) AS date,
  AVG(score) AS avg_score,
  COALESCE(SUM(duration_ms), 0) AS total_duration_ms,
  COUNT(id) AS session_count
FROM sessions
WHERE user_id = :uid
  AND started_at >= :lower_bound   -- omitido si range='all'
  AND module = :module             -- omitido si module='all'
GROUP BY DATE(started_at)
ORDER BY DATE(started_at);
```

El bucketing usa `DATE()` de PostgreSQL, que respeta el huso horario del servidor. Cloud SQL corre en UTC, así que los buckets son días UTC. Esto está alineado con cómo el script `seed_demo_user.py` genera las marcas temporales.

**Respuesta**

```json
{
  "range": "30d",
  "module": "all",
  "daily": [
    {
      "date": "2026-04-12",
      "avg_score": 67,
      "total_duration_ms": 1080000,
      "session_count": 3
    },
    {
      "date": "2026-04-13",
      "avg_score": null,
      "total_duration_ms": 360000,
      "session_count": 1
    }
  ]
}
```

- `avg_score` puede ser `null` si ese día solo hubo sesiones sin score (por ejemplo, sesiones `aborted`). Postgres `AVG` ignora `NULL`, así que el resultado del día puede no tener score aunque sí haya tiempo registrado.
- `total_duration_ms` siempre es entero ≥ 0 (`COALESCE` lo garantiza).
- Los días sin sesiones simplemente no aparecen en la lista. El frontend debe rellenarlos como huecos (o como 0) para el eje X continuo.

**Esquemas**

Pydantic: `app/presentation/schemas/profile.py` define `TimelinePoint`, `TimelineResponse` y el tipo `TimeRange`.
