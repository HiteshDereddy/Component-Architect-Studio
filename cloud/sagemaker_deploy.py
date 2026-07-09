import sagemaker
from sagemaker.model import Model
from sagemaker.serverless import ServerlessInferenceConfig

def deploy_to_sagemaker():
    """
    Deploys the custom ML worker Docker container to AWS SageMaker for scalable, 
    production-grade inference without needing to manage Kubernetes directly.
    """
    
    # IAM Role with permissions to SageMaker and ECR
    role = "arn:aws:iam::123456789012:role/SageMakerExecutionRole"
    
    # The Docker Image URI pushed to AWS Elastic Container Registry (ECR)
    # This image is built using backend/Dockerfile.worker
    image_uri = "123456789012.dkr.ecr.us-east-1.amazonaws.com/component-architect-worker:latest"
    
    # Initialize the SageMaker Model
    sm_model = Model(
        image_uri=image_uri,
        role=role,
        name="guided-component-architect-v1"
    )
    
    # Configure Serverless Inference (Automatically scales to zero when not in use)
    # This replaces the need for a Horizontal Pod Autoscaler (HPA)
    serverless_config = ServerlessInferenceConfig(
        memory_size_in_mb=6144, # 6GB RAM required for the 3B Granite model
        max_concurrency=10      # Max number of concurrent models to spin up during spikes
    )
    
    print("Deploying Model to SageMaker Serverless Endpoint...")
    
    # Deploy the endpoint
    predictor = sm_model.deploy(
        serverless_inference_config=serverless_config,
        endpoint_name="component-architect-endpoint"
    )
    
    print(f"Deployment successful! Endpoint Name: {predictor.endpoint_name}")
    print("The backend API Gateway can now route generation requests directly to this endpoint using Boto3.")

if __name__ == "__main__":
    deploy_to_sagemaker()
