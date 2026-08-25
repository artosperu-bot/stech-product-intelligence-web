# Desplegar STECH Product Intelligence Web en Render Free

Esta es la ruta principal para probar la Web V1 sin configurar Google Cloud Billing.

## Lo que despliega

Un unico **Web Service Docker** contiene:

- React/Vite compilado como frontend estatico.
- FastAPI como API.
- Python y la logica preservada de V30.
- Playwright + Chromium headless.
- Excel, imagenes, videos, yt-dlp e imageio-ffmpeg.

El archivo `render.yaml` ya fija `plan: free`, `runtime: docker`, `region: oregon`, health check y auto-deploy.

## Paso 1 - subir este proyecto a GitHub

Crea un repositorio vacio, por ejemplo:

`stech-product-intelligence-web`

Sube **el contenido de esta carpeta**, de forma que `Dockerfile` y `render.yaml` queden en la raiz del repositorio.

## Paso 2 - crear el servicio desde el Blueprint

1. Entra a Render con GitHub.
2. Pulsa **New** > **Blueprint**.
3. Selecciona el repositorio `stech-product-intelligence-web`.
4. Render detectara automaticamente `render.yaml`.
5. Comprueba que el servicio muestre **Free** antes de crear el Blueprint.
6. Pulsa **Apply / Deploy**.

No necesitas escribir manualmente el Build Command ni el Start Command: Render usara nuestro `Dockerfile`.

## Paso 3 - esperar el primer build

El primer build puede tardar porque instala el frontend y prepara la imagen con Playwright/Chromium.

Cuando termine, Render dara una URL parecida a:

`https://stech-product-intelligence-web.onrender.com`

Prueba primero:

`https://TU-URL.onrender.com/api/health`

Debe devolver un JSON con `ok: true` y los cuatro workflows.

Luego abre la raiz `/` para cargar la interfaz React.

## Importante sobre Render Free

La instancia gratuita es para pruebas y puede dormirse cuando queda inactiva. El primer acceso despues de dormir puede tardar mientras vuelve a arrancar.

Los archivos de trabajo se guardan en `/tmp/stech-product-intelligence` y son temporales. La idea es generar el XLSX/ZIP, descargarlo a tu PC y no usar Render como almacenamiento permanente.

El contenedor ejecuta un solo worker y Chromium tiene flags de bajo consumo para reducir picos de RAM. Aun asi, Playwright es la parte que debemos validar en el deploy real: si 512 MB no alcanzan, la web/API puede funcionar y el navegador puede necesitar otro host o un worker externo.

## Inicio de sesion de ChatGPT

La automatizacion conserva el mecanismo de V30, pero un servidor nuevo no tiene tu sesion local de ChatGPT.

Si ChatGPT permite trabajar sin una sesion exportada, no configures nada.

Si necesita tu sesion, usa localmente:

`python tools/export_chatgpt_state.py`

Ese archivo genera el estado Playwright. **No lo subas a GitHub.**

En Render puedes guardar el JSON como variable secreta:

`CHATGPT_STORAGE_STATE_JSON`

Hazlo desde **Environment** del servicio. Nunca publiques cookies, tokens o ese JSON en el repositorio.

## Auto deploy

`render.yaml` usa `autoDeployTrigger: commit`.

Despues del primer enlace:

`git push` -> Render construye -> Render despliega.

## Si falla el primer deploy

No cambies varias cosas a la vez. Copia desde Render:

- el final del **Build Log** si falla construyendo;
- el **Deploy Log** si construye pero no inicia;
- el log de la investigacion si inicia pero falla Chromium/ChatGPT.

Con eso podemos distinguir build, memoria, Playwright y autenticacion sin adivinar.
