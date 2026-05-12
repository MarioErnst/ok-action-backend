# Módulo de Videos y Almacenamiento en S3 (Backblaze B2)

Este módulo gestiona las cápsulas de aprendizaje (videos) utilizadas en la plataforma. Para garantizar escalabilidad, seguridad y bajo costo, el almacenamiento de los videos está desacoplado del servidor y utiliza **Backblaze B2** mediante la interfaz compatible con AWS S3 (`boto3`).

## Almacenamiento en la Nube (Backblaze B2)

Los archivos físicos **no** se almacenan localmente en la carpeta `backend/uploads/`, sino que se alojan de forma segura en un bucket de Backblaze B2.
Para esto, se utiliza la librería `boto3` configurada con un `endpoint_url` personalizado.

### Configuración de Entorno (`.env`)
El módulo requiere las siguientes variables de entorno para funcionar:
- `S3_BUCKET`: Nombre del bucket (ej. `ok-actionbucket`).
- `AWS_REGION`: Región del bucket (ej. `us-east-005`).
- `S3_ENDPOINT_URL`: URL del endpoint de Backblaze (ej. `https://s3.us-east-005.backblazeb2.com`).
- `AWS_ACCESS_KEY_ID`: Key ID generado en la plataforma B2.
- `AWS_SECRET_ACCESS_KEY`: Application Key (secreta) generada en B2.

### Generación de URLs Firmadas (Presigned URLs)
Para evitar que el bucket sea público y prevenir el robo de ancho de banda o acceso no autorizado, los videos se entregan al Frontend mediante **URLs firmadas temporalmente**.
La función `get_presigned_url(s3_key: str)` del archivo `app.infrastructure.backblaze_setup` genera un enlace seguro (válido típicamente por 1 hora) que permite descargar o reproducir el archivo directamente desde Backblaze.

## Endpoints
- **GET /api/videos**: Retorna la lista de todos los videos desde la Base de Datos. En lugar de devolver una ruta estática (ej. `/uploads/video.mp4`), el caso de uso se encarga de generar al vuelo una URL firmada de S3 para cada video.
- *(Nota: Las operaciones de subida y eliminación operan directamente contra los objetos del bucket S3 en Backblaze).*
