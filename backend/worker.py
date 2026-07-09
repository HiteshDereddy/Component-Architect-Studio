"""
worker.py — Redis queue consumer for inference worker pods.

This worker runs inside the Kubernetes pods to scale ML inference.
It pulls generation requests from a Redis queue, runs them through the 
GuidedComponentArchitect, and pushes results back to Redis for the API 
pod to stream to the client using Server-Sent Events (SSE).
"""

import json
import os
import time
import redis
from llama_cpp import Llama
from agent import GuidedComponentArchitect

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REQUEST_QUEUE = "generation:requests"
RESULT_PREFIX = "generation:results:"
RESULT_TTL = 300  # seconds

def get_model_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "models", "granite-4.1-3b-q4_k_m.gguf")

def main():
    print(f"[Worker] Connecting to Redis: {REDIS_URL}")
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    print("[Worker] Redis connected.")

    model_path = get_model_path()
    print(f"[Worker] Loading ML model into memory from {model_path}...")
    
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1,
        n_ctx=5120,
        verbose=False
    )
    architect = GuidedComponentArchitect(llm)
    print("[Worker] Model loaded. Listening for requests on queue...")

    while True:
        # BRPOP blocks until a message arrives
        item = r.brpop(REQUEST_QUEUE, timeout=5)
        if item is None:
            continue

        _, raw = item
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[Worker] Invalid JSON in queue: {exc}")
            continue

        request_id = request.get("request_id", "unknown")
        prompt = request.get("prompt", "")
        current_code = request.get("current_code", None)
        result_key = f"{RESULT_PREFIX}{request_id}"

        print(f"[Worker] Processing request {request_id}: {prompt[:80]}...")

        try:
            # Generate and stream tokens to the Redis list
            for chunk in architect.generate(prompt, current_code=current_code, stream=True):
                r.rpush(result_key, json.dumps({"type": "chunk", "content": chunk}))
                # Set TTL on result key to prevent memory leaks
                r.expire(result_key, RESULT_TTL)
            
            # Send final completion event
            r.rpush(result_key, json.dumps({"type": "done"}))
        except Exception as e:
            print(f"[Worker] Error generating component: {e}")
            r.rpush(result_key, json.dumps({"type": "error", "content": str(e)}))
            r.rpush(result_key, json.dumps({"type": "done"}))

        print(f"[Worker] Request {request_id} completed.")

if __name__ == "__main__":
    main()
