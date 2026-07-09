# AWS SageMaker Deployment

This directory contains scripts and configs for deploying the Granite 3B model
as a SageMaker real-time inference endpoint.

## Architecture

```
User → Angular Frontend (S3 + CloudFront)
         ↓
       FastAPI Backend (ECS / EC2)
         ↓
       SageMaker Real-Time Endpoint (Granite 3B GGUF)
```

## Prerequisites

- AWS CLI configured (`aws configure`)
- An S3 bucket for model artifacts
- IAM role with SageMaker execution permissions
- Docker (for building the custom inference container)

## Deployment Steps

### 1. Upload model to S3

```bash
aws s3 cp backend/models/granite-4.1-3b-q4_k_m.gguf \
  s3://YOUR_BUCKET/models/granite-4.1-3b-q4_k_m.gguf
```

### 2. Build and push the inference container

```bash
cd deploy/sagemaker
docker build -t granite-inference -f Dockerfile.sagemaker ../../backend
# Tag and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
docker tag granite-inference:latest YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/granite-inference:latest
docker push YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/granite-inference:latest
```

### 3. Create the SageMaker endpoint

```bash
python deploy/sagemaker/create_endpoint.py
```

### 4. Update backend to use the SageMaker endpoint

Set the following environment variables on the FastAPI backend:

```bash
GENERATION_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=https://runtime.sagemaker.us-east-1.amazonaws.com/endpoints/granite-endpoint/invocations
OPENAI_COMPATIBLE_API_KEY=<sagemaker-session-token>
OPENAI_COMPATIBLE_MODEL=granite-3b
```

The `openai-compatible` provider in `generator.py` will route generation
requests to the SageMaker endpoint seamlessly.
