$ErrorActionPreference = "Stop"
$Region = if ($env:REGION) { $env:REGION } else { "us-central1" }
$Service = if ($env:SERVICE) { $env:SERVICE } else { "stech-product-intelligence" }
$ProjectId = if ($env:PROJECT_ID) { $env:PROJECT_ID } else { (gcloud config get-value project 2>$null).Trim() }

if (-not $ProjectId -or $ProjectId -eq "(unset)") {
    throw "Configura un proyecto primero: gcloud config set project TU_PROJECT_ID"
}

Write-Host "Proyecto: $ProjectId"
Write-Host "Habilitando APIs necesarias..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project $ProjectId

Write-Host "Desplegando $Service en $Region..."
gcloud run deploy $Service `
  --source . `
  --project $ProjectId `
  --region $Region `
  --allow-unauthenticated `
  --memory 2Gi `
  --cpu 1 `
  --timeout 3600 `
  --concurrency 1 `
  --max-instances 1 `
  --set-env-vars STECH_HEADLESS=true
