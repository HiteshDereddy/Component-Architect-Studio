"""
deploy_endpoint.py — Deploy Granite 3B as a GCP Vertex AI online prediction endpoint.

Usage:
    python deploy/vertex-ai/deploy_endpoint.py

Prerequisites:
    pip install google-cloud-aiplatform
    gcloud auth application-default login
"""

import os
from google.cloud import aiplatform

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "YOUR_PROJECT_ID")
REGION = os.getenv("GCP_REGION", "us-central1")
IMAGE_URI = os.getenv(
    "VERTEX_IMAGE_URI",
    f"us-docker.pkg.dev/{PROJECT_ID}/granite-repo/granite-inference:latest",
)
MODEL_GCS_URI = os.getenv(
    "VERTEX_MODEL_GCS",
    "gs://YOUR_BUCKET/models/",
)
MACHINE_TYPE = os.getenv("VERTEX_MACHINE_TYPE", "n1-standard-4")
ACCELERATOR_TYPE = os.getenv("VERTEX_ACCELERATOR_TYPE", "NVIDIA_TESLA_T4")
ACCELERATOR_COUNT = int(os.getenv("VERTEX_ACCELERATOR_COUNT", "1"))
ENDPOINT_DISPLAY_NAME = "granite-component-architect"
MODEL_DISPLAY_NAME = "granite-3b-component-gen"


def main():
    aiplatform.init(project=PROJECT_ID, location=REGION)

    # Upload model
    print(f"Uploading model from {IMAGE_URI}...")
    model = aiplatform.Model.upload(
        display_name=MODEL_DISPLAY_NAME,
        serving_container_image_uri=IMAGE_URI,
        serving_container_ports=[8080],
        serving_container_environment_variables={
            "MODEL_PATH": "/opt/ml/model/granite-4.1-3b-q4_k_m.gguf",
            "GENERATION_PROVIDER": "llama",
            "LLAMA_GPU_LAYERS": "-1",
            "LLAMA_CONTEXT_SIZE": "4096",
            "LLAMA_MAX_TOKENS": "900",
        },
        artifact_uri=MODEL_GCS_URI,
    )
    print(f"  Model uploaded: {model.resource_name}")

    # Create endpoint
    print(f"Creating endpoint: {ENDPOINT_DISPLAY_NAME}")
    endpoint = aiplatform.Endpoint.create(display_name=ENDPOINT_DISPLAY_NAME)
    print(f"  Endpoint created: {endpoint.resource_name}")

    # Deploy model to endpoint
    print("Deploying model to endpoint...")
    model.deploy(
        endpoint=endpoint,
        deployed_model_display_name=MODEL_DISPLAY_NAME,
        machine_type=MACHINE_TYPE,
        accelerator_type=ACCELERATOR_TYPE,
        accelerator_count=ACCELERATOR_COUNT,
        min_replica_count=1,
        max_replica_count=3,
        traffic_percentage=100,
    )
    print(f"  Model deployed to {endpoint.resource_name}")
    print(f"\nDone. Endpoint ID: {endpoint.name}")
    print(f"Prediction URL: https://{REGION}-aiplatform.googleapis.com/v1/{endpoint.resource_name}:predict")


if __name__ == "__main__":
    main()
