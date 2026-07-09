"""
create_endpoint.py — Deploy Granite 3B as an AWS SageMaker real-time inference endpoint.

Usage:
    python deploy/sagemaker/create_endpoint.py

Prerequisites:
    pip install boto3
    aws configure  (with SageMaker permissions)
"""

import boto3
import os
import time

REGION = os.getenv("AWS_REGION", "us-east-1")
ROLE_ARN = os.getenv("SAGEMAKER_ROLE_ARN", "arn:aws:iam::YOUR_ACCOUNT:role/SageMakerExecutionRole")
IMAGE_URI = os.getenv("SAGEMAKER_IMAGE_URI", "YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/granite-inference:latest")
MODEL_DATA_URL = os.getenv("SAGEMAKER_MODEL_S3", "s3://YOUR_BUCKET/models/granite-4.1-3b-q4_k_m.gguf")
ENDPOINT_NAME = os.getenv("SAGEMAKER_ENDPOINT_NAME", "granite-component-architect")
INSTANCE_TYPE = os.getenv("SAGEMAKER_INSTANCE_TYPE", "ml.g5.xlarge")

sagemaker = boto3.client("sagemaker", region_name=REGION)

model_name = f"{ENDPOINT_NAME}-model-{int(time.time())}"
config_name = f"{ENDPOINT_NAME}-config-{int(time.time())}"


def create_model():
    print(f"Creating SageMaker model: {model_name}")
    sagemaker.create_model(
        ModelName=model_name,
        PrimaryContainer={
            "Image": IMAGE_URI,
            "ModelDataUrl": MODEL_DATA_URL,
            "Environment": {
                "MODEL_PATH": "/opt/ml/model/granite-4.1-3b-q4_k_m.gguf",
                "GENERATION_PROVIDER": "llama",
                "LLAMA_GPU_LAYERS": "-1",
                "LLAMA_CONTEXT_SIZE": "4096",
                "LLAMA_MAX_TOKENS": "900",
            },
        },
        ExecutionRoleArn=ROLE_ARN,
    )
    print(f"  Model created: {model_name}")


def create_endpoint_config():
    print(f"Creating endpoint config: {config_name}")
    sagemaker.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[
            {
                "VariantName": "primary",
                "ModelName": model_name,
                "InstanceType": INSTANCE_TYPE,
                "InitialInstanceCount": 1,
                "InitialVariantWeight": 1.0,
            }
        ],
    )
    print(f"  Config created: {config_name}")


def create_endpoint():
    print(f"Creating endpoint: {ENDPOINT_NAME}")
    sagemaker.create_endpoint(
        EndpointName=ENDPOINT_NAME,
        EndpointConfigName=config_name,
    )
    print(f"  Endpoint creation initiated. Waiting for InService status...")

    waiter = sagemaker.get_waiter("endpoint_in_service")
    waiter.wait(EndpointName=ENDPOINT_NAME, WaiterConfig={"Delay": 30, "MaxAttempts": 60})
    print(f"  Endpoint {ENDPOINT_NAME} is InService!")


if __name__ == "__main__":
    create_model()
    create_endpoint_config()
    create_endpoint()
    print(f"\nDone. Endpoint URL: https://runtime.sagemaker.{REGION}.amazonaws.com/endpoints/{ENDPOINT_NAME}/invocations")
