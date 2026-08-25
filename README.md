# STECH Product Intelligence Web V1


## Despliegue recomendado para prueba gratuita: Render

Para la primera prueba sin Google Cloud Billing, este paquete incluye `render.yaml` con un unico Web Service Docker en `plan: free`. Render compila React, inicia FastAPI y ejecuta Playwright/Chromium dentro del mismo contenedor.

Pasos completos: **`DESPLEGAR_RENDER.md`**.

Cloud Run sigue disponible como alternativa mediante `DESPLEGAR_GOOGLE_CLOUD.md`, pero no es necesario para probar la version de Render.


Versión web de **Mi Buscador AutoFill V30**. La interfaz Tkinter se reemplaza por una SPA React, mientras la lógica de negocio V30 sigue en Python: detección de plantillas Excel, segunda pasada de características, validación, precios, imágenes, videos y descargas.

## Arquitectura de esta primera versión

```text
Navegador (React)
      │
      │ NDJSON streaming: progreso + logs + resultados
      ▼
FastAPI ──────────────────────┐
      │                       │
      ▼                       │
V30 Core (Python)             │
      │                       │
      ├─ Características      │
      ├─ Precios Perú         │
      ├─ Imágenes             │
      └─ Videos               │
      │                       │
      ▼                       │
Playwright + Chromium         │
      │                       │
      └──────── archivos temporales (/tmp)
                              │
                              ▼
                        descarga al navegador
```

Todo está en **un solo contenedor y un solo Web Service Docker** para que el primer despliegue sea lo más simple posible. El destino recomendado para la prueba gratuita es Render; Cloud Run queda como alternativa.

## Qué incluye

- 4 vistas web: **Características / Precios Perú / Imágenes / Videos**.
- Cambio de vista instantáneo; cada vista conserva su resultado mientras navegas.
- Progreso por etapas y por cantidad real cuando el workflow expone `actual/total`.
- Logs en vivo y botón de diagnóstico desde la web.
- Características conserva el flujo seguro de V30: primero vista previa; el Excel se genera solo cuando presionas **GENERAR EXCEL**.
- La hoja `IA_CARACTERISTICAS` continúa siendo responsabilidad del `template_engine.py` original de V30.
- Precios usa las pasadas y verificación web de V30.
- Imágenes y videos conservan ranking/identidad/descarga de V30.
- ZIP de imágenes/videos seleccionados.
- `NUEVO PRODUCTO` limpia resultados pero conserva la plantilla seleccionada en el navegador.

## Importante: ChatGPT en un servidor Linux

V30 automatiza `chatgpt.com` mediante Playwright. En Render o Cloud Run Chromium se ejecuta **headless**.

La aplicación intenta funcionar con la experiencia pública de ChatGPT. Si ChatGPT exige autenticación o bloquea el navegador del datacenter, usa el mecanismo opcional `CHATGPT_STORAGE_STATE_JSON`.

Hay un asistente local:

```bash
python tools/export_chatgpt_state.py
```

que abre Chromium en tu PC para que inicies sesión manualmente y genera `chatgpt_storage_state.json`. Ese archivo contiene sesión/cookies y **nunca debe subirse a GitHub**.

Esta es la principal variable que queremos comprobar en la prueba real de Render. El resto de la lógica V30 corre dentro del contenedor.

## Despliegue rápido en Google Cloud Run

### 1. Instala Google Cloud CLI

Instala `gcloud` y luego:

```bash
gcloud auth login
```

Selecciona o crea un proyecto y configúralo:

```bash
gcloud config set project TU_PROJECT_ID
```

### 2. Habilita servicios

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

### 3. Despliega desde esta carpeta

Windows PowerShell:

```powershell
.\deploy-cloud-run.ps1
```

Linux/macOS:

```bash
./deploy-cloud-run.sh
```

O directamente:

```bash
gcloud run deploy stech-product-intelligence \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 1 \
  --timeout 3600 \
  --concurrency 1 \
  --max-instances 1 \
  --set-env-vars STECH_HEADLESS=true
```

Cloud Run usa el `Dockerfile` del repositorio y construye la imagen automáticamente.

### ¿1 GiB o 2 GiB?

Para una primera prueba puedes cambiar `--memory 2Gi` por `--memory 1Gi`. Para Playwright + Chromium + imágenes/videos, **2 GiB es la configuración más segura**. Si el uso es ocasional, el nivel gratuito puede seguir cubriendo bastantes horas de ejecución, pero Google Cloud requiere una cuenta de facturación activa para ser elegible para su Free Tier.

### Por qué `concurrency=1` y `max-instances=1` en Web V1

Esta versión inicial conserva estado de trabajo y archivos descargables temporalmente en el proceso y en `/tmp`. Una sola instancia evita que el resultado termine en una instancia distinta de la que atiende el botón de descarga.

Cuando confirmemos que la web y Chromium funcionan correctamente, la siguiente mejora sería mover estado/archivos a Supabase o Cloud Storage; ahí podremos escalar a múltiples instancias.

## Login opcional de ChatGPT mediante Secret Manager

Después de crear localmente `chatgpt_storage_state.json`, evita pasarlo como texto en el comando. Puedes guardarlo como secreto:

```bash
gcloud services enable secretmanager.googleapis.com

gcloud secrets create stech-chatgpt-storage-state --replication-policy=automatic

gcloud secrets versions add stech-chatgpt-storage-state --data-file=chatgpt_storage_state.json
```

Luego configura el servicio para exponer el secreto como variable `CHATGPT_STORAGE_STATE_JSON` (la cuenta de servicio de Cloud Run necesita permiso para leer ese secreto).

## Desarrollo local sin Docker

Backend:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements.txt
python -m playwright install chromium
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8080 --reload
```

Frontend, en otra consola:

```bash
cd frontend
npm install
npm run dev
```

Vite proxyea `/api` a `http://127.0.0.1:8080`.

## Docker local

```bash
docker build -t stech-product-intelligence .
docker run --rm -p 8080:8080 -e PORT=8080 stech-product-intelligence
```

Abre `http://localhost:8080`.

## Estructura

```text
frontend/                 React + Vite
backend/app/              API y adaptación web/Cloud Run
backend/legacy_core/      lógica Python copiada byte-a-byte desde V30
tools/                    utilidades de despliegue/login
docs/superpowers/         diseño + plan técnico
Dockerfile                contenedor único Web V1
deploy-cloud-run.ps1      despliegue desde Windows
deploy-cloud-run.sh       despliegue Linux/macOS
```

## Archivos temporales

Web V1 guarda resultados en `/tmp/stech-product-intelligence` durante un tiempo limitado (por defecto 30 minutos). En Cloud Run ese filesystem no es almacenamiento permanente. Esto es deliberado para la primera prueba: generas → descargas a tu PC → expira.

Para videos grandes conviene seleccionar solo los que realmente quieras descargar; el archivo temporal consume memoria/espacio de la instancia mientras se prepara el ZIP.

## Variables

Consulta `.env.example`.

- `STECH_HEADLESS=true`
- `ARTIFACT_TTL_MINUTES=30`
- `CHATGPT_STORAGE_STATE_JSON=` opcional y sensible
- `STECH_CHATGPT_RUNTIME_STATE=` opcional; ubicación del estado renovado dentro de la instancia

## GitHub

El proyecto está listo para un repositorio nuevo. Si tienes GitHub CLI instalado:

```bash
git init
git add .
git commit -m "feat: STECH Product Intelligence Web V1"
git branch -M main
gh repo create artosperu-bot/stech-product-intelligence-web --private --source=. --remote=origin --push
```

Si creas el repositorio vacío desde github.com, también puedes conectar `origin` y hacer `git push` normalmente.
