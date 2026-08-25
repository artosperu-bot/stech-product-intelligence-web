# Desplegar STECH Product Intelligence Web V1 en Google Cloud Run

## Camino corto

Desde PowerShell, dentro de la raíz del proyecto:

```powershell
gcloud auth login
gcloud config set project TU_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
.\deploy-cloud-run.ps1
```

Al terminar, `gcloud` mostrará la URL pública del servicio.

## Primera prueba recomendada

1. Abre `/api/health` y confirma `"ok": true`.
2. Abre la raíz del sitio y revisa las 4 vistas.
3. Prueba Características con un Excel real.
4. Si el log llega a Chromium pero ChatGPT exige login, genera `chatgpt_storage_state.json` con `tools/export_chatgpt_state.py` y configúralo mediante Secret Manager.
5. Solo después prueba Precios, Imágenes y Videos.

## Configuración inicial

- Región: `us-central1` para aprovechar precios de referencia del free tier.
- CPU: `1`
- RAM: `2Gi` para comenzar; prueba `1Gi` si quieres reducir consumo.
- Concurrencia: `1`
- Máximo de instancias: `1`
- Timeout: `3600` segundos.

## Lo que queremos comprobar

La mayor incógnita no es React ni FastAPI. Es si `chatgpt.com` permite la sesión Playwright headless desde el datacenter de Cloud Run. Por eso el sistema tiene logs detallados y soporte para storage state.
