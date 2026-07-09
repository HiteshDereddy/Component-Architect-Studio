# GCP Vertex AI Deployment

This directory contains scripts and configs for deploying the Granite 3B model
as a Vertex AI online prediction endpoint.

## Architecture

```
User → Angular Frontend (Cloud Run / Firebase Hosting)
         ↓
       FastAPI Backend (Cloud Run)
         ↓
       Vertex AI Online Prediction Endpoint (Granite 3B GGUF)
```

## Prerequisites

- Google Cloud CLI (`gcloud`) configured
- A GCS bucket for model artifacts
- Artifact Registry repository for Docker images
- Vertex AI API enabled

## Deployment Steps

### 1. Upload model to GCS

```bash
gsutil cp backend/models/granite-4.1-3b-q4_k_m.gguf \
  gs://YOUR_BUCKET/models/granite-4.1-3b-q4_k_m.gguf
```

### 2. Build and push the inference container

```bash
cd deploy/vertex-ai
gcloud builds submit \
  --tag us-docker.pkg.dev/YOUR_PROJECT/granite-repo/granite-inference:latest \
  ../../backend
```

### 3. Deploy to Vertex AI

```bash
python deploy/vertex-ai/deploy_endpoint.py
```

### 4. Update backend to use the Vertex AI endpoint

Set the following environment variables on the FastAPI backend:

```bash
GENERATION_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=https://us-central1-aiplatform.googleapis.com/v1/projects/YOUR_PROJECT/locations/us-central1/endpoints/ENDPOINT_ID
OPENAI_COMPATIBLE_API_KEY=$(gcloud auth print-access-token)
OPENAI_COMPATIBLE_MODEL=granite-3b
```
