# Script `seed_demo_user.py`

Crea (o regenera) el usuario demo "Mario Jr" con 60 días de actividad sintética para poder grabar la demo del producto contra una cuenta con historial.

Ubicación: `backend/scripts/seed_demo_user.py`.

## Qué hace

1. Conecta a Cloud SQL usando la misma configuración (`.env`) que el resto de la app.
2. Garantiza que exista el rol `user` (lo crea si no existe).
3. Busca al usuario `mario@okaction.cl`. Si no existe lo crea con `Demo1234!` como password (hash bcrypt).
4. Borra **todas** las sesiones previas de Mario Jr. El `ON DELETE CASCADE` de la FK arrastra también sus métricas hijas. El usuario y el rol se preservan.
5. Genera ~117 sesiones repartidas en 60 días hacia atrás desde "ahora" (UTC), cubriendo los 12 módulos del `ModuleEnum` salvo `live`.

Idempotente: correrlo dos veces seguidas deja la BD en el mismo estado (con un seed aleatorio fijo, los datos generados son reproducibles).

## Credenciales del usuario demo

| Campo | Valor |
|---|---|
| Email | `mario@okaction.cl` |
| Password | `Demo1234!` |
| Nombre | `Mario Jr` |

## Cómo se generan los datos

| Parámetro | Valor | Significado |
|---|---|---|
| `NUM_DAYS` | 60 | Largo de la ventana temporal. |
| `AVG_DAILY_MINUTES` | 26 | Media del tiempo total diario antes de truncados/saltos. El promedio efectivo después de descartes ronda los 20 min/día. |
| `DAILY_MINUTES_SIGMA` | 9 | Desviación estándar del tiempo diario. Algunos días son cortos, otros más largos. |
| `SKIP_DAY_PROBABILITY` | 0.12 | Probabilidad de que un día no tenga actividad (días "off"). |
| `MAX_SESSIONS_PER_DAY` | 4 | Tope superior; en la práctica la mayoría de días tienen 1-3 sesiones. |
| `RANDOM_SEED` | 42 | Semilla fija para que el output sea reproducible. |

### Curva de rendimiento

Cada módulo tiene su propia curva de mejora desde un score inicial (~45-60) hacia un score final (~78-88), con ruido gaussiano de sigma 6 por sesión. La curva avanza linealmente con el día.

**Excepción intencional**: `linguistic_versatility` arranca en 35 y termina en 65. Es el "talón de Aquiles" de Mario para que se vea contraste cuando se filtra por módulo en el dashboard.

`live` queda fuera porque es un wrapper de composición; sus métricas se computarían como agregado de sus hijos, así que generar sesiones standalone de `live` distorsionaría el gráfico.

## Cómo correrlo

Pre-requisito: el schema tiene que estar al día (`alembic upgrade head`) y el `.env` del backend debe tener las credenciales de Cloud SQL configuradas.

Desde la carpeta `backend/`:

```bash
source venv/bin/activate
python -m scripts.seed_demo_user
```

Salida esperada (segunda corrida en adelante incluye el "Wiped"):

```
Wiped 117 existing sessions for mario@okaction.cl
Seeded 117 sessions for mario@okaction.cl across 12 modules over 60 days
```

## Cuándo correrlo

- Antes de grabar la demo del producto.
- Después de un reset del schema (`alembic downgrade base && alembic upgrade head`).
- Si querés regenerar la data porque las fechas quedaron desfasadas (las marcas son relativas a `now()` cuando corre el script).

## Limitaciones conocidas

- **Solo se popula `sessions`**, no las tablas `<modulo>_metrics`. Esto es suficiente para los gráficos del dashboard (que consumen solo `score`, `duration_ms`, `started_at`, `module` y `user_id`). Las pantallas de detalle por sesión van a mostrar las tarjetas vacías de métricas detalladas.
- Las sesiones siempre se crean en estado `completed` con `parent_id = NULL`. No se generan composiciones live.
- Los timestamps están en UTC. Si grabás la demo desde una zona horaria muy desfasada (>4h), los buckets diarios pueden no coincidir exactamente con tu calendario local.
