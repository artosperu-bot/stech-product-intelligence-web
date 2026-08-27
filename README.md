# STECH Product Intelligence Web V1

Versión web de Mi Buscador AutoFill V30 preparada para Render Free.

## Acceso

Por defecto, un Web Service de Render expone una URL pública. Para una prueba interna, no compartas la URL ni cargues credenciales o cookies en el repositorio. La protección de acceso se puede añadir como siguiente paso.

## Estado del despliegue

El Dockerfile incluye verificación SHA-256 del núcleo V30 antes de iniciar la aplicación. Si el bundle de transferencia pierde solo el trailer gzip/tar, la extracción continúa únicamente si los 26 archivos Python resultantes coinciden exactamente con el hash esperado y compilan correctamente.

Consulta `DESPLEGAR_RENDER.md` para el flujo de despliegue.
