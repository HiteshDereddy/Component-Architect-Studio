import json
import os
from llama_cpp import Llama

base_dir = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(base_dir, "backend", "models", "granite-4.1-3b-q4_k_m.gguf")

llm = Llama(
    model_path=model_path,
    n_ctx=8192,
    n_threads=4,
    n_gpu_layers=-1,
    verbose=False
)

system_prompt = "You are a coding assistant. Write a long HTML file."
prompt = "<|start_of_role|>system<|end_of_role|>\n" + system_prompt + "<|end_of_text|>\n<|start_of_role|>user<|end_of_role|>\nWrite a very long HTML page<|end_of_text|>\n<|start_of_role|>assistant<|end_of_role|>\n"

print("Generating...")
stream = llm(
    prompt,
    max_tokens=8192,
    stop=["<|end_of_text|>", "<|start_of_role|>"],
    echo=False,
    temperature=0.1,
    stream=True
)

for chunk in stream:
    print(chunk["choices"][0]["text"], end="", flush=True)
print("\nDone.")
