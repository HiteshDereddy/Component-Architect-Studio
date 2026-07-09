from __future__ import annotations

import json
import re
import time
from threading import Event
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph


class AgentState(TypedDict, total=False):
    prompt: str
    generated_code: str
    errors: list[str]
    iterations: int
    history: list[dict[str, str]]
    metrics: dict[str, Any]


class AgentGraph:
    """Orchestrates generation, validation, and self-repair as a real state machine."""

    def __init__(self, generator: Any, validator: Any, max_iterations: int = 3):
        self.generator = generator
        self.validator = validator
        self.max_iterations = max_iterations
        self.app = self._build_graph()

    def generate_events(self, prompt: str, cancel_event: Event | None = None, thinking_enabled: bool = True, current_code: list[dict] = None):
        started_at = time.perf_counter()
        state: AgentState = {
            "prompt": prompt,
            "errors": [],
            "iterations": 0,
            "history": [],
            "metrics": {},
        }

        while state["iterations"] < self.max_iterations:
            if cancel_event and cancel_event.is_set():
                yield {"type": "cancelled"}
                return

            is_fix = state["iterations"] > 0
            generated_code = ""
            first_token_at = None
            # Only track think block if thinking is enabled for this request
            in_think_block = thinking_enabled and not is_fix
            emitted_thinking_len = 0

            stream_gen = self.generator.generate_component_stream(
                state.get("history", []),
                state["prompt"],
                is_fix=is_fix,
                thinking_enabled=thinking_enabled,
            )
            for chunk in stream_gen:
                if cancel_event and cancel_event.is_set():
                    stream_gen.close()
                    yield {"type": "cancelled"}
                    return
                if chunk and first_token_at is None:
                    first_token_at = time.perf_counter()
                generated_code += chunk

                if not is_fix:
                    if in_think_block:
                        # Detect transition: </think> OR start of first code block (whichever comes first)
                        transition_at = -1
                        skip_marker = 0  # chars to skip over the transition marker itself

                        end_tag_idx = generated_code.find("</think>")
                        if end_tag_idx != -1:
                            transition_at = end_tag_idx
                            skip_marker = len("</think>")

                        if transition_at != -1:
                            # Transition: send remaining thinking text, then code tail
                            in_think_block = False
                            new_thinking = generated_code[emitted_thinking_len:transition_at]
                            if new_thinking.strip():
                                yield {"type": "thinking", "content": new_thinking}
                            code_tail = generated_code[transition_at + skip_marker:]
                            if code_tail:
                                yield {"type": "chunk", "content": code_tail}
                        else:
                            # Still thinking — emit only new chars since last emit
                            new_thinking = generated_code[emitted_thinking_len:]
                            if new_thinking:
                                yield {"type": "thinking", "content": new_thinking}
                            emitted_thinking_len = len(generated_code)
                    else:
                        yield {"type": "chunk", "content": chunk}

                if self._has_complete_component(generated_code):
                    break

            from normalizer import normalize_markdown_code
            normalized_code = normalize_markdown_code(generated_code)
            
            # Auto-merge missing blocks from current_code (for follow-ups where LLM was lazy)
            if current_code and not is_fix:
                existing_blocks = self.validator._extract_code_blocks(normalized_code)
                for block in current_code:
                    lang = getattr(block, 'language', '') if hasattr(block, 'language') else block.get('language', '')
                    code = getattr(block, 'code', '') if hasattr(block, 'code') else block.get('code', '')
                    if lang in ['typescript', 'html', 'css'] and lang not in existing_blocks:
                        normalized_code += f"\n\n```{lang}\n{code}\n```\n"
                        yield {"type": "chunk", "content": f"\n\n```{lang}\n{code}\n```\n"}
            
            state["generated_code"] = normalized_code
            state["iterations"] += 1
            state["errors"] = self.validator.validate(normalized_code)
            if state["errors"]:
                print(f"Validation failed with errors: {state['errors']}")
            state["metrics"] = {
                "first_token_ms": round((first_token_at - started_at) * 1000) if first_token_at else None,
                "total_ms": round((time.perf_counter() - started_at) * 1000),
                "iterations": state["iterations"],
                "validation_errors": state["errors"],
                "provider": getattr(self.generator, "provider", "unknown"),
            }

            if not state["errors"]:
                if is_fix:
                    yield {"type": "replace", "code": normalized_code}
                yield {"type": "done", "code": normalized_code, "metrics": state["metrics"]}
                return

            state = self._prepare_retry(state)

        yield {"type": "error", "errors": state.get("errors", []), "metrics": state.get("metrics", {})}

    def invoke(self, prompt: str) -> AgentState:
        return self.app.invoke({
            "prompt": prompt,
            "errors": [],
            "iterations": 0,
            "history": [],
        })

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("generate", self._generate_node)
        graph.add_node("validate", self._validate_node)
        graph.add_node("prepare_retry", self._prepare_retry)

        graph.set_entry_point("generate")
        graph.add_edge("generate", "validate")
        graph.add_conditional_edges(
            "validate",
            self._route_after_validation,
            {
                "retry": "prepare_retry",
                "done": END,
            },
        )
        graph.add_edge("prepare_retry", "generate")
        return graph.compile()

    def _generate_node(self, state: AgentState) -> AgentState:
        is_fix = state.get("iterations", 0) > 0
        generated_code = ""
        for chunk in self.generator.generate_component_stream(
            state.get("history", []),
            state["prompt"],
            is_fix=is_fix,
        ):
            generated_code += chunk
            if self._has_complete_component(generated_code):
                break

        from normalizer import normalize_markdown_code
        normalized_code = normalize_markdown_code(generated_code)
        return {
            **state,
            "generated_code": normalized_code,
            "iterations": state.get("iterations", 0) + 1,
        }

    def _validate_node(self, state: AgentState) -> AgentState:
        return {
            **state,
            "errors": self.validator.validate(state.get("generated_code", "")),
        }

    def _route_after_validation(self, state: AgentState) -> Literal["retry", "done"]:
        if not state.get("errors"):
            return "done"
        if state.get("iterations", 0) >= self.max_iterations:
            return "done"
        return "retry"

    def _prepare_retry(self, state: AgentState) -> AgentState:
        history = list(state.get("history", []))
        history.append({"role": "user", "content": state["prompt"]})
        history.append({"role": "assistant", "content": state.get("generated_code", "")})

        return {
            **state,
            "history": history,
            "prompt": self._repair_prompt(state.get("errors", [])),
        }

    def _repair_prompt(self, errors: list[str]) -> str:
        formatted_errors = "\n".join(f"- {error}" for error in errors)
        return f"""CRITICAL FIX REQUIRED.
Your previous output failed validation.

Fix every validation error below and output the complete Angular component again.
IMPORTANT: If the error mentions unauthorized colors, YOU MUST REPLACE THE HARDCODED HEX/RGB COLORS WITH A VALID CSS VARIABLE (e.g., `var(--primary)` or `var(--surface)`). Look at the system rules for the exact list of allowed variables. Do NOT simply pick a different hex color!

You MUST output exactly three markdown blocks in this order:
```typescript
```html
```css

<validation_errors>
{formatted_errors}
</validation_errors>

Do not output explanations, XML patches, partial files, or text outside the three code blocks."""

    def _has_complete_component(self, generated_code: str) -> bool:
        blocks = {
            language.lower(): code
            for language, code in re.findall(r"```(\w+)\s*\n(.*?)```", generated_code, flags=re.DOTALL)
        }
        if "ts" in blocks:
            blocks["typescript"] = blocks["ts"]
        return all(blocks.get(language, "").strip() for language in ("typescript", "html", "css"))


def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
