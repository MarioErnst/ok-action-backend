# Módulo de Videos

Este módulo permite gestionar videos físicos en la aplicación.

## Endpoints

- **GET /videos**: Retorna la lista de todos los videos subidos, incluyendo su id, título, url y nombre de archivo.
- **POST /videos/upload**: Recibe un archivo de video (`file: UploadFile`) y un título (`title: Form`). Guarda el archivo en la carpeta `backend/uploads/` con un nombre único y retorna la información del video.
- **DELETE /videos/{id}**: Elimina la información del video y el archivo físico asociado en base al ID proporcionado.

## Almacenamiento
- Los archivos físicos se almacenan localmente en la carpeta `backend/uploads/`.
- La información estructurada de los videos se guarda temporalmente en un archivo JSON local `backend/videos.json`.
