# Despliegue en Cloud Run

## Descripción

Este documento describe la configuración de contenedor Docker para desplegar el backend de OK Action en Google Cloud Run.

## Archivos de configuración

### `Dockerfile`

Ubicado en la raíz del repositorio. Usa `python:3.12-slim` como imagen base para mantener el tamaño reducido.

El proceso de construcción:
1. Copia `backend/requirements.txt` e instala todas las dependencias con pip.
2. Copia el contenido de `backend/` al directorio de trabajo `/app` dentro del contenedor.
3. Expone el puerto **8080**, que es el puerto fijo requerido por Cloud Run.
4. Arranca la aplicación con `uvicorn main:app --host 0.0.0.0 --port 8080`.

Se eligió Python 3.12 (no la versión local 3.14) porque es la versión estable más reciente disponible en Docker Hub con imagen slim oficial.

### `.dockerignore`

Excluye del contexto de construcción:
- `backend/venv/` — entorno virtual local, no debe ir en la imagen
- `backend/__pycache__/` y `*.pyc` — bytecode generado localmente
- `backend/.env` y variantes — nunca se incluyen credenciales en la imagen
- `backend/tests/` — los tests no son necesarios en producción
- Archivos de configuración local (`CLAUDE.md`, `.gcloudignore`, `.gitignore`)

## Variables de entorno

El contenedor no incluye ningún valor sensible. Todas las variables deben configurarse en Cloud Run al momento del despliegue:

| Variable | Descripción |
|---|---|
| `APP_NAME` | Nombre de la aplicación |
| `ENVIRONMENT` | `production` en Cloud Run |
| `GCP_PROJECT_ID` | ID del proyecto GCP |
| `GCP_REGION` | Región de la instancia Cloud SQL |
| `GCP_INSTANCE_NAME` | Nombre de la instancia Cloud SQL |
| `DB_USER` | Usuario de la base de datos |
| `DB_PASSWORD` | Contraseña de la base de datos |
| `DB_NAME` | Nombre de la base de datos |
| `JWT_SECRET_KEY` | Clave secreta para firmar tokens JWT |
| `JWT_ALGORITHM` | Algoritmo JWT (por defecto `HS256`) |
| `JWT_EXPIRE_MINUTES` | Tiempo de expiración del token en minutos |
| `CORS_ORIGINS` | Lista JSON de orígenes permitidos |
| `GEMINI_API_KEY` | Clave de la API de Gemini |
| `S3_BUCKET` | Nombre del bucket Backblaze B2 (por defecto `ok-actionbucket`). |
| `S3_ENDPOINT_URL` | Endpoint S3 de Backblaze (por defecto `https://s3.us-east-005.backblazeb2.com`). |
| `AWS_REGION` | Región del bucket (por defecto `us-east-005`). Se mantiene el prefijo `AWS_*` por convención boto3. |
| `AWS_ACCESS_KEY_ID` | `keyID` del Application Key generado en la consola de Backblaze. |
| `AWS_SECRET_ACCESS_KEY` | `applicationKey` del Application Key. Solo visible una vez al crear la key. |

## Credenciales de GCP (Cloud SQL Connector)

El módulo `session.py` usa el Cloud SQL Python Connector, que requiere credenciales de GCP para conectarse a Cloud SQL.

En Cloud Run, esto se resuelve automáticamente: cada servicio de Cloud Run tiene asociado un service account que actúa como Application Default Credentials (ADC). No se necesita ningún archivo de credenciales en la imagen.

Requisito: el service account del servicio Cloud Run debe tener el rol **Cloud SQL Client** (`roles/cloudsql.client`) en IAM.

## Prueba local

Para correr el contenedor en local es necesario montar credenciales de GCP, ya que el Cloud SQL Connector las requiere al inicializarse:

```bash
docker build -t ok-action-backend .
docker run --rm \
  --env-file backend/.env \
  -v ~/.config/gcloud/application_default_credentials.json:/tmp/adc.json \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json \
  -p 8080:8080 \
  ok-action-backend
```

Las credenciales locales se obtienen con `gcloud auth application-default login`.

## Flujo de despliegue

1. Se hace merge de `feature/docker-cloudrun` → `develop` → `main`.
2. Cloud Run está configurado para apuntar a la rama `main` del repositorio.
3. Cada push a `main` dispara una nueva construcción de la imagen y un despliegue automático.
