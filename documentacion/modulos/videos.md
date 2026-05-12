# Módulo de Cápsulas de Video

Las cápsulas de aprendizaje del producto. La metadata (id, título) vive en Postgres; el archivo físico vive en un bucket privado de Backblaze B2 al que se accede vía S3 API.

## Arquitectura

```
┌─────────────┐      HTTP        ┌──────────────────┐      SQL        ┌────────────────┐
│  Frontend   │  ─────────────►  │  FastAPI router  │  ────────────►  │  Postgres      │
│             │   /api/videos    │  + use cases     │                 │  tabla videos  │
└─────────────┘                  └────────┬─────────┘                 └────────────────┘
                                          │ boto3 (S3 API)
                                          ▼
                                ┌──────────────────────┐
                                │  Backblaze B2 bucket │
                                │  ok-actionbucket     │
                                │  prefix `videos/`    │
                                └──────────────────────┘
```

La decisión clave: **metadata desacoplada del binario**. El bucket no codifica títulos en el filename; cada objeto vive bajo `videos/{uuid}.{ext}` y la tabla `videos` guarda el título legible. Esto evita los problemas del esquema viejo, donde el filename `{uuid}_{título}` era frágil ante guiones bajos en el título y obligaba a parsear texto para recuperar la metadata.

## Tabla `videos`

Migración: `alembic/versions/0003_add_videos_table.py`.

| Columna | Tipo | Nota |
|---|---|---|
| `id` | UUID PK | Identificador estable del video. |
| `title` | VARCHAR(255) | Nombre legible para mostrar al usuario. |
| `s3_key` | VARCHAR(512) UNIQUE | Key del objeto en Backblaze (ej. `videos/3f8c2d11-….mp4`). UNIQUE para impedir filas que apunten al mismo binario. |
| `created_at` | TIMESTAMPTZ | Default `now()` server-side. |

Entidad SQLAlchemy: `app/domain/entities/video.py`.

## Capas

| Archivo | Responsabilidad |
|---|---|
| `app/domain/entities/video.py` | Entidad SQLAlchemy. |
| `app/presentation/schemas/videos.py` | `VideoResponse` (DTO HTTP). Incluye `url` presigned generada al vuelo. |
| `app/infrastructure/repositories/video_repository.py` | Queries async: `list_all`, `get_by_id`, `create`, `delete_row`. |
| `app/infrastructure/backblaze_setup.py` | Cliente boto3 + helper `get_presigned_url`. Lee credenciales desde `config.settings`. |
| `app/use_cases/video_use_cases.py` | Orquesta bucket + DB: `list_videos`, `upload_video`, `delete_video`. Async, recibe `AsyncSession`. |
| `app/presentation/routers/video_router.py` | Endpoints `/api/videos`. Async. `delete` recibe `UUID`. |

## Endpoints

| Método | Path | Descripción |
|---|---|---|
| `GET` | `/api/videos` | Lista todas las cápsulas. Devuelve `[{id, title, url, filename}]` con `url` válida 1h. |
| `POST` | `/api/videos/upload` | Sube un video. `multipart/form-data` con `file` y `title`. Genera UUID, sube al bucket, persiste fila. |
| `DELETE` | `/api/videos/{video_id}` | Borra el video. Primero elimina del bucket, luego la fila. Si Backblaze falla, la fila queda y se puede reintentar. |

## Configuración de entorno

Centralizada en `config.py` (`Settings` de Pydantic). Variables en `.env`:

| Variable | Default | Significado |
|---|---|---|
| `S3_BUCKET` | `ok-actionbucket` | Nombre del bucket. |
| `S3_ENDPOINT_URL` | `https://s3.us-east-005.backblazeb2.com` | Endpoint S3 de Backblaze. |
| `AWS_REGION` | `us-east-005` | Región Backblaze (mantenemos el nombre `AWS_*` por convención boto3). |
| `AWS_ACCESS_KEY_ID` | `""` | `keyID` del Application Key generado en la consola de Backblaze. |
| `AWS_SECRET_ACCESS_KEY` | `""` | `applicationKey`. Solo visible una vez al crear el Application Key. |

Los tres primeros tienen defaults sensibles; los dos secretos quedan en blanco y son obligatorios para que el servicio funcione.

## Garantías y orden de operaciones

**Upload (`upload_video`)**:
1. Subir el binario al bucket.
2. Persistir la fila en Postgres.
3. Commit.

Si (2) falla, queda un objeto huérfano en el bucket que se puede limpiar con una pasada manual. Es preferible a tener una fila apuntando a un binario inexistente.

**Delete (`delete_video`)**:
1. Buscar la fila (404 si no existe).
2. Borrar el objeto del bucket.
3. Borrar la fila.
4. Commit.

Si (2) falla, el bucket aún tiene el objeto y la fila también — el usuario reintenta. Si fallara (3), el bucket ya borró el objeto y queda una fila apuntando a algo que no está; por eso (2) va primero solo cuando estamos seguros que la fila existe.

## Seed de cápsulas existentes

Script: `backend/scripts/seed_existing_videos.py`. Lista los objetos del bucket e inserta una fila por cada uno que aún no esté en la tabla. Idempotente: re-ejecutarlo nunca duplica filas.

Comando:

```bash
cd backend
./venv/bin/python -m scripts.seed_existing_videos
```

Los nombres se asignan así:
- Objetos que matcheen `video (N).ext` → título `"Cápsula N"`.
- Cualquier otro → enumeración secuencial alfabética: `"Cápsula 1"`, `"Cápsula 2"`, ...

## Presigned URLs

`get_presigned_url(s3_key, expiration=3600)` en `backblaze_setup.py` genera un GET firmado válido 1 hora. El bucket permanece privado; ninguna URL pública existe.

Como `list_videos` genera la URL en cada llamada al endpoint, la TTL siempre es completa para el usuario que la recibe.
