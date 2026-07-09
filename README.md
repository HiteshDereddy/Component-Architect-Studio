# Guided Component Architect

An enterprise-grade, agentic code-generation platform that transforms natural language descriptions into valid, styled Angular components while strictly adhering to a predefined Design System. 

This repository implements the core building blocks of platforms like Lovable or Bolt.new, featuring a robust multi-agent workflow, self-correction loops, Guardrails AI security, and production-ready Kubernetes ML scaling.

---

## Features & Technical Nuances

### 1. Agentic Code Generation & Context Management
Translates user prompts into clean Angular code (`HTML`, `TS`, `CSS`) and strips conversational filler.
- **Design System Enforcement:** Dynamically injects a strict JSON design token schema (colors, fonts, radii) into the LLM context.
- **Context Preservation:** Implements advanced prompt history formatting that flattens previous markdown block tags, preventing nested-markdown syntax hallucinations in the LLM during iterative "follow-up" code modifications.
- **Metal GPU Offloading:** Utilizes `llama-cpp-python` with `-DLLAMA_METAL=on` / CUDA flags for native hardware acceleration during local inference.

### 2. Automated Validation & Self-Correction (Linter-Agent)
An integrated Linter-Agent intercepts the raw LLM output and validates it before returning it to the user.
- **AST-Based CSS Normalization:** Uses custom parsers to ensure generated CSS strictly maps to the design system. For example, if the LLM hallucinates `#ff0000`, the normalizer intelligently attempts to map it, or flags it.
- **Autonomous Feedback Loop:** If the generated syntax is malformed, the backend catches the error and autonomously re-prompts the LLM with the error logs to "fix" the component in the background.

### 3. Guardrails AI Security Firewall
A robust input firewall that instantly blocks Prompt Injections (Jailbreaks), Profanity, Personally Identifiable Information (PII), and leaked AWS Secrets.
- **Deterministic Regex Fallbacks:** Implements custom `RegexMatch` validators with optimized multiline/ignore-case flags to bypass the unreliability of local HuggingFace NLP models.
- **Graceful Re-ask Handling:** Wraps the Guardrails validation step in a custom exception handler to catch internal `litellm` credential crashes, translating them into standard `HTTP 403 Forbidden` responses.

### 4. Interactive Live Preview
A stunning, reactive UI built in Angular.
- **Server-Sent Events (SSE) Streaming:** The backend streams code generation chunks to the frontend in real-time, complete with typewriter effects.
- **Manual Edit Mode:** Features a manual "Edit Code" toggle that unlocks the code viewer, allowing developers to manually tweak the generated Angular code and hit "Render" to safely live-update the UI without polluting the LLM's history state.
- **Dynamic Compilation:** Dynamically builds and renders the generated Angular component in an isolated preview host without requiring a page refresh.

### 5. Production-Grade Distributed Infrastructure
Fully decoupled backend architecture designed for high availability.
- **Queue-Based Inference:** Replaces blocking FastAPI endpoints with an `/async-generate` route that pushes jobs to a Redis message broker, freeing up the API gateway.
- **Celery ML Workers:** Dedicated inference worker pods that pop jobs from Redis and stream the generated tokens back to a Redis list for the gateway to relay via SSE.
- **Kubernetes Autoscaling (HPA):** Custom K8s manifests dynamically scale the heavy ML Worker pods from 1 to 20 based on CPU load and queue depth.
- **AWS SageMaker Serverless:** Includes Python SDK deployment scripts mapping the Dockerized ML Worker to an AWS SageMaker Serverless endpoint, demonstrating native cloud autoscaling without maintaining Kubernetes.

---

## Tech Stack

- **Frontend:** Angular 17+ (Standalone Components, TypeScript, CSS)
- **Backend Gateway:** FastAPI (Python, Uvicorn, SSE Streaming)
- **ML Inference Engine:** `llama-cpp-python` (Metal GPU Offloading, Granite 4.1 3B Instruct)
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

Note on Vercel: While the Angular frontend can be effortlessly deployed to Vercel, the Python backend cannot be deployed to Vercel Serverless Functions. Vercel has a 250MB size limit, which makes it impossible to host a 2GB+ `.gguf` local ML model. To use Vercel for the backend, you would need to swap `llama-cpp-python` for a cloud API provider like Groq, OpenAI, or TogetherAI.

### Option A: Kubernetes & Autoscaling (HPA)
We have provided a decoupled architecture where the FastAPI gateway pushes jobs to a Redis queue, and dedicated ML Worker pods process them.
1. Apply the Redis Broker: `kubectl apply -f k8s/redis-deployment.yaml`
2. Apply the API Gateway: `kubectl apply -f k8s/api-deployment.yaml`
3. Apply the ML Workers & HPA: `kubectl apply -f k8s/worker-deployment.yaml` and `k8s/hpa-scaling.yaml`

### Option B: AWS SageMaker Serverless
For a fully managed infrastructure, use the provided SageMaker deployment script. This wraps the ML Worker in a Docker container and deploys it to a Serverless Endpoint that automatically scales to zero.
- Review and run: `python cloud/sagemaker_deploy.py`
