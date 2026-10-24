#!/usr/bin/env bash
# Deploy Resume Verifier AI to Google Cloud: Cloud Run + Cloud SQL.
# Fill in PROJECT_ID and REGION before running. Secrets must already exist
# in Secret Manager: AUTH_SECRET, DB_PASSWORD, and optionally RESEND_API_KEY.
# This script does NOT create or print secret values.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-phonic-oxide-508515-k1}"
REGION="${REGION:-us-central1}"  # confirmed by user 2026-10-24
INSTANCE_NAME="${INSTANCE_NAME:-resume-verifier-db}"
DB_NAME="${DB_NAME:-resume_verifier}"
DB_USER="${DB_USER:-resume}"
REPO="${REPO:-resume-verifier}"
BACKEND_SERVICE="${BACKEND_SERVICE:-resume-verifier-backend}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-resume-verifier-frontend}"

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com

gcloud artifacts repositories create "$REPO" --repository-format=docker \
  --location="$REGION" --description="Resume Verifier AI images" 2>/dev/null || true

BACKEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/backend:latest"
FRONTEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/frontend:latest"

gcloud builds submit --tag "$BACKEND_IMAGE" backend
# Frontend is built after the backend URL is known (NEXT_PUBLIC_API_URL is
# baked in at build time), so the frontend build happens below.

gcloud sql instances create "$INSTANCE_NAME" --database-version=POSTGRES_16 \
  --tier=db-g1-small --region="$REGION" --root-password="$(gcloud secrets versions access latest --secret=DB_PASSWORD)" 2>/dev/null || true
gcloud sql databases create "$DB_NAME" --instance="$INSTANCE_NAME" 2>/dev/null || true
gcloud sql users create "$DB_USER" --instance="$INSTANCE_NAME" \
  --password="$(gcloud secrets versions access latest --secret=DB_PASSWORD)" 2>/dev/null || true

INSTANCE_CONNECTION="$PROJECT_ID:$REGION:$INSTANCE_NAME"
DATABASE_URL="postgresql+psycopg://$DB_USER:$(gcloud secrets versions access latest --secret=DB_PASSWORD)@/$DB_NAME?host=/cloudsql/$INSTANCE_CONNECTION"

# NOTE: passing DATABASE_URL on the command line exposes it in shell history.
# Prefer storing the full URL as a Secret Manager secret and using
# --set-secrets=DATABASE_URL=resume-db-url:latest instead in production.
gcloud run deploy "$BACKEND_SERVICE" --image "$BACKEND_IMAGE" --region "$REGION" \
  --platform managed --allow-unauthenticated --port 8080 \
  --add-cloudsql-instances "$INSTANCE_CONNECTION" \
  --set-env-vars "DATABASE_URL=$DATABASE_URL" \
  --set-secrets "AUTH_SECRET=AUTH_SECRET:latest" \
  --set-env-vars "CORS_ORIGINS=https://PLACEHOLDER-FRONTEND-URL,AI_ENABLED=false"

BACKEND_URL="$(gcloud run services describe "$BACKEND_SERVICE" --region "$REGION" --format='value(status.url)')"
echo "Backend: $BACKEND_URL"

# Frontend: NEXT_PUBLIC_API_URL is baked in at build time, so build it
# locally (or in Cloud Shell, which has Docker) with the backend URL.
docker build --build-arg "NEXT_PUBLIC_API_URL=$BACKEND_URL" -t "$FRONTEND_IMAGE" frontend
docker push "$FRONTEND_IMAGE"
gcloud run deploy "$FRONTEND_SERVICE" --image "$FRONTEND_IMAGE" --region "$REGION" \
  --platform managed --allow-unauthenticated --port 8080

FRONTEND_URL="$(gcloud run services describe "$FRONTEND_SERVICE" --region "$REGION" --format='value(status.url)')"
echo "Frontend: $FRONTEND_URL"
gcloud run services update "$BACKEND_SERVICE" --region "$REGION" \
  --update-env-vars "CORS_ORIGINS=$FRONTEND_URL,FRONTEND_URL=$FRONTEND_URL"
echo "Backend CORS updated to $FRONTEND_URL"
