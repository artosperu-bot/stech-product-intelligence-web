#!/usr/bin/env bash
set -euo pipefail

REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-stech-product-intelligence}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "ERROR: configura un proyecto primero: gcloud config set project TU_PROJECT_ID" >&2
  exit 1
fi

echo "Proyecto: $PROJECT_ID"
echo "Habilitando APIs necesarias..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project "$PROJECT_ID"

echo "Desplegando $SERVICE en $REGION..."
gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 1 \
  --timeout 3600 \
  --concurrency 1 \
  --max-instances 1 \
  --set-env-vars STECH_HEADLESS=true
