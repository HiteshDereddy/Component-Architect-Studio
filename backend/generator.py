import json
import os
import time
import urllib.request
from threading import Lock
from llama_cpp import Llama

from system_prompt import get_system_prompt

class AngularComponentGenerator:
    def __init__(self, model_path: str, design_system_path: str):
        self.model_path = model_path
        self.design_system_path = design_system_path
        self.provider = os.getenv("GENERATION_PROVIDER", "llama").lower()
        self.llm = None
        self.llm_lock = Lock()

        # Load design system
        with open(design_system_path, "r") as f:
            self.design_system = json.load(f)

        self.max_tokens = int(os.getenv("LLAMA_MAX_TOKENS", "2048"))
        self.temperature = float(os.getenv("LLAMA_TEMPERATURE", "0.1"))

        if self.provider == "llama":
            self._load_llama()
        elif self.provider in {"openai-compatible", "template", "mock"}:
            print(f"Using generation provider: {self.provider}")
        else:
            raise ValueError(f"Unsupported GENERATION_PROVIDER: {self.provider}")

    def generate_component_stream(self, session_history: list, user_prompt: str, is_fix=False, thinking_enabled: bool = True):
        use_think = thinking_enabled and not is_fix
        system_prompt = get_system_prompt(self.design_system, thinking_enabled=use_think)

        if self.provider == "template":
            yield self._template_component(user_prompt)
            return

        if self.provider == "mock":
            yield from self._mock_stream(user_prompt, use_think_primer=use_think)
            return

        if self.provider == "openai-compatible":
            yield from self._openai_compatible_stream(system_prompt, session_history, user_prompt)
            return

        yield from self._llama_stream(system_prompt, session_history, user_prompt, use_think_primer=use_think)

    def _load_llama(self):
        print(f"Loading llama.cpp model from {self.model_path}...")
        context_size = int(os.getenv("LLAMA_CONTEXT_SIZE", "4096"))
        thread_count = int(os.getenv("LLAMA_THREADS", "4"))
        gpu_layers = int(os.getenv("LLAMA_GPU_LAYERS", "-1"))

        import llama_cpp
        self.llm = Llama(
            model_path=self.model_path,
            n_ctx=5120,
            n_threads=thread_count,
            n_gpu_layers=gpu_layers,
            use_mmap=True,
            flash_attn=True,
            verbose=False
        )

    def _llama_stream(self, system_prompt: str, session_history: list, user_prompt: str, use_think_primer: bool = False):
        # Granite 4.1 instruct format
        full_prompt = f"<|start_of_role|>system<|end_of_role|>\n{system_prompt}<|end_of_text|>\n"

        for msg in session_history:
            role = msg["role"]
            full_prompt += f"<|start_of_role|>{role}<|end_of_role|>\n{msg['content']}<|end_of_text|>\n"

        full_prompt += f"<|start_of_role|>user<|end_of_role|>\n{user_prompt}<|end_of_text|>\n"

        # Prime with <think> only when thinking is on
        if use_think_primer:
            full_prompt += f"<|start_of_role|>assistant<|end_of_role|>\n<think>\n"
        else:
            full_prompt += f"<|start_of_role|>assistant<|end_of_role|>\n"

        print(f"Generating (think={use_think_primer}), prompt_len={len(full_prompt)} chars")
        start_time = time.perf_counter()
        first_token_time = None

        with self.llm_lock:
            if use_think_primer:
                # Pass 1: Think (with penalty)
                stream = self.llm(
                    full_prompt,
                    max_tokens=2048,
                    stop=["</think>", "<|end_of_text|>", "<|start_of_role|>", "```"],
                    echo=False,
                    temperature=self.temperature,
                    repeat_penalty=1.15,
                    # repeat_last_n=128,
                    stream=True
                )
                thought_text = ""
                for chunk in stream:
                    text = chunk["choices"][0]["text"]
                    thought_text += text
                    if text and first_token_time is None:
                        first_token_time = time.perf_counter()
                        print(f"LLM first token: {first_token_time - start_time:.2f}s")
                    yield text

                yield "\n</think>\n\n"
                full_prompt += thought_text + "\n</think>\n\n"

                # Pass 2: Code (no penalty)
                stream = self.llm(
                    full_prompt,
                    max_tokens=self.max_tokens,
                    stop=["<|end_of_text|>", "<|start_of_role|>"],
                    echo=False,
                    temperature=self.temperature,
                    repeat_penalty=1.0,
                    stream=True
                )
                for chunk in stream:
                    text = chunk["choices"][0]["text"]
                    yield text
            else:
                stream = self.llm(
                    full_prompt,
                    max_tokens=self.max_tokens,
                    stop=["<|end_of_text|>", "<|start_of_role|>"],
                    echo=False,
                    temperature=self.temperature,
                    repeat_penalty=1.0,
                    stream=True
                )

                for chunk in stream:
                    text = chunk["choices"][0]["text"]
                    if text and first_token_time is None:
                        first_token_time = time.perf_counter()
                        print(f"LLM first token: {first_token_time - start_time:.2f}s")
                    yield text


    def _openai_compatible_stream(self, system_prompt: str, session_history: list, user_prompt: str):
        base_url = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "").rstrip("/")
        api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "")
        model = os.getenv("OPENAI_COMPATIBLE_MODEL", "")
        if not base_url or not api_key or not model:
            raise RuntimeError("OPENAI_COMPATIBLE_BASE_URL, OPENAI_COMPATIBLE_API_KEY, and OPENAI_COMPATIBLE_MODEL are required.")

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(session_history)
        messages.append({"role": "user", "content": user_prompt})
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        print(f"Generating with OpenAI-compatible provider: {model}")
        with urllib.request.urlopen(request, timeout=120) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content

    def _mock_stream(self, user_prompt: str, use_think_primer: bool = True):
        import time
        title = self._title_from_prompt(user_prompt)
        
        # Simulate thinking
        if use_think_primer:
            yield "<think>\n"
            think_text = (
                "1. User wants a new component design.\n"
                "2. I'll use a responsive flexbox layout to structure the elements.\n"
                "3. For the HTML, I'll need a main container section and some text blocks.\n"
                "4. The CSS will leverage design system tokens like var(--surface) and var(--spacing-large).\n"
                "5. Let's add a subtle glassmorphism effect and rounded corners to make it pop.\n"
                "</think>\n\n"
            )
            for char in think_text:
                yield char
                time.sleep(0.015)
                
        # Simulate code
        code = f"""```typescript
import {{ Component }} from '@angular/core';

@Component({{
  selector: 'app-generated-component',
  standalone: true,
  templateUrl: './generated.component.html',
  styleUrls: ['./generated.component.css']
}})
export class GeneratedComponent {{
  title = '{title}';
}}
```
```html
<section class="generated-shell">
  <h2>{{{{ title }}}}</h2>
  <p>Simulated output for testing the UI stream.</p>
</section>
```
```css
.generated-shell {{
  padding: var(--spacing-large);
  background: var(--surface);
  border-radius: var(--border-radius);
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}}
```
"""
        for i in range(0, len(code), 3):
            yield code[i:i+3]
            time.sleep(0.01)

    def _template_component(self, user_prompt: str) -> str:
        title = self._title_from_prompt(user_prompt)
        return f"""```typescript
import {{ Component }} from '@angular/core';

@Component({{
  selector: 'app-generated-component',
  standalone: true,
  templateUrl: './generated.component.html',
  styleUrls: ['./generated.component.css']
}})
export class GeneratedComponent {{
  title = '{title}';
}}
```
```html
<section class="generated-shell bg-glassmorphism">
  <p class="eyebrow">Guided Component Architect</p>
  <h2 class="text-headings h2">{{{{ title }}}}</h2>
  <p class="summary">A polished generated component using the active design system.</p>
  <button class="btn btn-primary">Continue</button>
</section>
```
```css
.generated-shell {{
  width: min(100%, 420px);
  padding: var(--spacing-large);
  border-radius: var(--radius);
  color: var(--textPrimary);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.28);
}}
.eyebrow {{
  margin: 0 0 var(--spacing-small);
  color: var(--secondary);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
}}
.summary {{
  color: var(--textSecondary);
  margin: 0 0 var(--spacing-medium);
}}
```
"""

    def _title_from_prompt(self, prompt: str) -> str:
        words = [word.strip(".,:;!?()[]{}'\"") for word in prompt.split()]
        title_words = [word.capitalize() for word in words[:4] if word]
        return " ".join(title_words) or "Generated Component"

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_path = os.path.join(base_dir, "backend", "models", "granite-4.1-3b-q4_k_m.gguf")
    design_system_path = os.path.join(base_dir, "design-system.json")
    
    if os.path.exists(model_path):
        generator = AngularComponentGenerator(model_path, design_system_path)
        prompt = "A modern login card with an email and password field, a submit button, and a glassmorphism effect."
        
        print("\n--- STARTING GENERATION ---")
        print("\n--- GENERATED CODE ---\n")
        # Consume the stream
        for chunk in generator.generate_component_stream([], prompt):
            print(chunk, end="", flush=True)
        print("\n")
    else:
        print(f"Error: Model not found at {model_path}")
