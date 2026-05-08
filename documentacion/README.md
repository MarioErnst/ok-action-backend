# Documentación Técnica — OK Action Backend

## Propósito

Esta carpeta contiene la documentación técnica del backend de OK Action. Sirve como referencia para desarrolladores que se incorporan al proyecto, facilitando la comprensión de la arquitectura, los módulos disponibles, los modelos de datos y los patrones de integración utilizados.

## Módulos Documentados

| Módulo | Archivo |
|--------|---------|
| Fonación | [modulos/fonacion.md](modulos/fonacion.md) |
| Pronunciación | [modulos/pronunciacion.md](modulos/pronunciacion.md) |
| Acentuación | [modulos/acentuacion.md](modulos/acentuacion.md) |
| Volumen | [modulos/volumen.md](modulos/volumen.md) |
| Muletillas | [modulos/muletillas.md](modulos/muletillas.md) |
| Pausas | [modulos/pausas.md](modulos/pausas.md) |
| Fluidez | [modulos/fluidez.md](modulos/fluidez.md) |

## Convenciones

### Idioma y Lenguaje

- Toda la documentación técnica se redacta en español.
- Se utiliza lenguaje formal y técnico, evitando jerga innecesaria.
- Los términos en inglés se mantienen cuando son estándar de la industria.

### Estructura de Documentación de Módulos

Cada documento de módulo sigue la siguiente estructura de 7 secciones:

1. **Descripción funcional**: Explica qué hace el módulo, su propósito y alcance.
2. **Capas del módulo**: Describe la arquitectura interna (router, schemas, use cases, entities, AI service).
3. **Modelo de datos**: Define las tablas de base de datos, columnas, tipos y relaciones.
4. **Esquemas de solicitud y respuesta**: Especifica los contratos Pydantic para la API.
5. **Casos de uso**: Describe la lógica de negocio implementada en cada función.
6. **Integración con Gemini AI**: Documenta cómo y cuándo se utiliza la API de Gemini (cuando aplique).
7. **Endpoints de la API**: Lista los endpoints disponibles, métodos HTTP, parámetros y respuestas esperadas.

### Agregar Documentación de un Nuevo Módulo

Para documentar un nuevo módulo:

1. Crear un archivo `modulos/nombre_del_modulo.md`.
2. Seguir la estructura de 7 secciones descrita arriba.
3. Agregar una fila a la tabla de "Módulos Documentados" con el nombre y enlace relativo.
4. Mantener la coherencia en formato, terminología y nivel de detalle con los módulos existentes.
5. Revisar que no haya inconsistencias con la documentación de otros módulos.
