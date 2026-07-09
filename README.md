# Component Architect Studio

An enterprise-grade, agentic code-generation platform that transforms natural language descriptions into valid, styled Angular components while strictly adhering to a predefined Design System. 

This repository implements the core building blocks of platforms like Lovable or Bolt.new, featuring a robust multi-agent workflow, self-correction loops, Guardrails AI security, and production-ready Kubernetes ML scaling.

---

## Features

- **Agentic Code Generation:** Translates user prompts into clean Angular code (`HTML`, `TS`, `CSS`) and strips conversational filler. Implements advanced prompt history formatting that flattens previous markdown tags to prevent nested-syntax hallucinations during iterative follow-ups.
- **Design System Enforcement:** Injects a strict JSON design token schema (colors, fonts, radii) into the LLM context.
- **Automated Validation & Self-Correction:** An integrated Linter-Agent intercepts the raw LLM output, validating syntax and mapping hallucinated variables to strict CSS variables via custom AST parsing. If the model outputs malformed code, the Linter-Agent automatically triggers a self-correction loop in the background.
- **Guardrails AI Security:** A robust input firewall that instantly blocks Prompt Injections (Jailbreaks), Profanity, Personally Identifiable Information (PII), and leaked AWS Secrets. Integrates deterministic Regex fallbacks to bypass unreliable local NLP models, and gracefully intercepts internal `litellm` credential crashes to translate them into clean HTTP 403 Forbidden responses.
- **Live Edit Mode:** A stunning glassmorphism UI that streams tokens in real-time via Server-Sent Events (SSE). Features a manual "Edit Code" toggle that unlocks the editor, allowing developers to manually tweak the generated Angular code and trigger dynamic component compilation without polluting the LLM's history state.
- **Advanced Code Export:** Developers can seamlessly download the generated code. Provides options to export the raw Angular component files (`.html`, `.ts`, `.css`) or compile them into a unified `.tsx` (React) equivalent structure for cross-framework portability.
- **Production-Grade Infrastructure:** Fully decoupled backend architecture utilizing a Redis message broker, Celery ML workers, and Kubernetes Autoscaling (HPA) for handling heavy traffic spikes.

---

## Tech Stack

- **Frontend:** Angular 17+ (Standalone Components, TypeScript, CSS)
- **Backend Gateway:** FastAPI (Python, Uvicorn, SSE Streaming)
- **ML Inference Engine:** `llama-cpp-python` (Metal GPU Offloading via `-DLLAMA_METAL=on`, Granite 4.1 3B Instruct)
- **Security:** Guardrails AI
- **Infrastructure:** Redis, Celery, Docker, Kubernetes (HPA), AWS SageMaker

---

## Getting Started (Local Development)

### 1. Download the ML Model Weights

Because LLM weights are massive (several gigabytes), they are excluded from source control. You must download the `.gguf` model file and place it in the `backend/models/` directory.

1. Download the Granite 3B GGUF Model from HuggingFace (e.g., [IBM Granite GGUF Repository](https://huggingface.co/ibm-granite)).
2. Create the models directory: `mkdir -p backend/models`
3. Place the downloaded `.gguf` file inside `backend/models/` and rename it to exactly: `granite-4.1-3b-q4_k_m.gguf`

### 2. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the synchronous FastAPI gateway for local development
uvicorn main:app --host 127.0.0.1 --port 8010
```

### 3. Frontend Setup
```bash
cd frontend
npm install

# Start the Angular development server
npm start
```

Navigate to `http://localhost:4200` to interact with the Component Architect.

---

## Enterprise Cloud Deployment

To deploy this architecture to a production environment where multiple users can generate code simultaneously, you must use the provided Kubernetes or AWS SageMaker scaffolding. 

> **Note on Vercel:** While the Angular frontend can be effortlessly deployed to Vercel, the Python backend **cannot** be deployed to Vercel Serverless Functions. Vercel has a 250MB size limit, which makes it impossible to host a 2GB+ `.gguf` local ML model. To use Vercel for the backend, you would need to swap `llama-cpp-python` for a cloud API provider like Groq, OpenAI, or TogetherAI.

### Option A: Kubernetes & Autoscaling (HPA)
We have provided a decoupled architecture where the FastAPI gateway pushes jobs to a Redis queue, and dedicated ML Worker pods process them.
1. Apply the Redis Broker: `kubectl apply -f k8s/redis-deployment.yaml`
2. Apply the API Gateway: `kubectl apply -f k8s/api-deployment.yaml`
3. Apply the ML Workers & HPA: `kubectl apply -f k8s/worker-deployment.yaml` and `k8s/hpa-scaling.yaml`

### Option B: AWS SageMaker Serverless
For a fully managed infrastructure, use the provided SageMaker deployment script. This wraps the ML Worker in a Docker container and deploys it to a Serverless Endpoint that automatically scales to zero.
- Review and run: `python cloud/sagemaker_deploy.py`

---

## Security Architecture

This repository implements **Guardrails AI** to prevent malicious use of the system. 
The firewall is configured in `backend/main.py` and uses a combination of Regex heuristics and local HuggingFace ML models (like `Presidio` for PII) to intercept:
- **Prompt Injection:** Blocking attempts to bypass system instructions.
- **Toxic Language:** Filtering out profanity.
- **PII / Secrets:** Preventing the model from generating or processing user emails, SSNs, or AWS keys.

Any violation instantly returns an `HTTP 403 Forbidden` error, protecting the expensive ML inference engine from wasting resources on bad actors.
