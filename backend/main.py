from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event
import difflib
import re
import subprocess
import time
from guardrails import Guard
from guardrails.hub import PromptInjectionDetector, ToxicLanguage, DetectPII, SecretsPresent, RegexMatch

# Pre-compile the Guards independently to prevent chaining shortcut bugs
try:
    safe_pattern = r"(?i)^(?![\s\S]*?(ignore all previous instructions|fucking|shit))[\s\S]*$"
    guards = [
        Guard().use(RegexMatch(regex=safe_pattern, on_fail="exception")),
        Guard().use(ToxicLanguage(threshold=0.5, validation_method="sentence", on_fail="exception")),
        Guard().use(DetectPII(pii_entities=["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN"], on_fail="exception")),
        Guard().use(SecretsPresent(on_fail="exception"))
    ]
except Exception as e:
    print(f"Warning: Guardrails AI not fully configured yet. {e}")
    guards = []

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import json
import os
import uuid
import redis

# Redis Configuration for Distributed K8s Scaling
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
except Exception:
    redis_client = None

REQUEST_QUEUE = "generation:requests"
RESULT_PREFIX = "generation:results:"

from generator import AngularComponentGenerator
from validator import CodeValidator
from normalizer import fix_css_variables, normalize_ts_code
from agent import AgentGraph, sse_event

def resolve_project_path(*parts: str) -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_sessions()
    model_path = os.getenv(
        "MODEL_PATH",
        resolve_project_path("backend", "models", "granite-4.1-3b-q4_k_m.gguf"),
    )
    design_system_path = os.getenv(
        "DESIGN_SYSTEM_PATH",
        resolve_project_path("design-system.json"),
    )

    app.state.generator = None
    app.state.validator = None
    app.state.agent = None
    app.state.model_error = None
    app.state.design_system_path = design_system_path

    if not os.path.exists(design_system_path):
        app.state.model_error = f"Design system not found at {design_system_path}"
        print(f"WARNING: {app.state.model_error}")
        yield
        return

    app.state.validator = CodeValidator(design_system_path)

    generation_provider = os.getenv("GENERATION_PROVIDER", "llama").lower()
    app.state.generation_provider = generation_provider
    if generation_provider == "llama" and not os.path.exists(model_path):
        app.state.model_error = f"Model not found at {model_path}"
        print(f"WARNING: {app.state.model_error}")
        yield
        return

    try:
        generator = AngularComponentGenerator(model_path, design_system_path)
        app.state.generator = generator
        app.state.agent = AgentGraph(generator, app.state.validator)
    except Exception as exc:
        app.state.model_error = str(exc)
        print(f"WARNING: Model failed to load: {exc}")

    yield


app = FastAPI(title="Guided Component Architect API", lifespan=lifespan)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:4200,http://127.0.0.1:4200").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    current_code: list[dict[str, str]] = Field(default_factory=list)
    thinking_enabled: bool = Field(default=True)

class PreviewPublishRequest(BaseModel):
    code_blocks: list[dict[str, str]]

class SnapshotRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code_blocks: list[dict[str, str]] = Field(default_factory=list)
    note: str = Field(default="")

sessions: dict[str, dict] = {}
active_requests: dict[str, Event] = {}
sessions_path = Path(__file__).resolve().parent / "runtime" / "sessions.json"
metrics = {
    "generation_requests_total": 0,
    "generation_success_total": 0,
    "generation_error_total": 0,
    "generation_cancelled_total": 0,
    "validation_error_total": 0,
    "preview_publish_total": 0,
    "preview_publish_error_total": 0,
    "version_restore_total": 0,
    "snapshot_total": 0,
    "generation_failures": 0,
}

def load_sessions() -> None:
    global sessions
    try:
        if sessions_path.exists():
            sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"WARNING: Failed to load sessions: {exc}")

def save_sessions() -> None:
    try:
        sessions_path.parent.mkdir(parents=True, exist_ok=True)
        sessions_path.write_text(json.dumps(sessions, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"WARNING: Failed to save sessions: {exc}")

@app.post("/generate")
def generate_code(request: GenerateRequest, fastapi_request: Request):
    metrics["generation_requests_total"] += 1
    prompt = request.prompt
    
    # Validate input with Guardrails AI to prevent prompt injection and toxicity
    if guards and not request.current_code:
        for guard in guards:
            try:
                outcome = guard.validate(prompt)
                print(f"GUARDRAILS OUTCOME: {outcome}", flush=True)
                if hasattr(outcome, "validation_passed"):
                    if outcome.validation_passed is False:
                        raise ValueError("Guardrails validation failed")
            except Exception as e:
                error_str = str(e)
                print(f"GUARDRAILS EXCEPTION: {error_str}", flush=True)
                if "Missing credentials" in error_str or "litellm" in error_str:
                    # Guardrails tried to reask the LLM because a validator failed. Treat as blocked.
                    pass 
                metrics["generation_failures"] += 1
                raise HTTPException(status_code=403, detail="Security Error: Prompt Injection or Toxic Language detected by Guardrails AI.")

    agent = fastapi_request.app.state.agent

    if not agent:
        detail = fastapi_request.app.state.model_error or "Generator or Validator not loaded."
        raise HTTPException(status_code=503, detail=detail)
        
    def stream_generator():
        session = sessions.setdefault(request.session_id, {
            "session_id": request.session_id,
            "history": [],
            "versions": [],
            "created_at": time.time(),
        })
        cancel_event = Event()
        active_requests[request.session_id] = cancel_event
        session["history"].append({"role": "user", "content": request.prompt, "at": time.time()})
        
        # If the frontend sent existing code, we are doing a follow-up
        if request.current_code:
            current_code_md = ""
            for block in request.current_code:
                current_code_md += f"--- {block['language'].upper()} ---\n{block['code']}\n\n"
                
            final_prompt = (
                f"CURRENT COMPONENT STATE:\n{current_code_md}\n"
                f"USER FOLLOW-UP REQUEST: {prompt}\n\n"
                "Revise the current component to satisfy the follow-up. "
                "Think first inside <think> tags, then output the 3 code blocks. "
                "Return the full updated component using exactly three markdown blocks: "
                "```typescript, ```html, and ```css. Do not output XML patches or prose outside the think block."
            )
        else:
            # We are generating a new component
            final_prompt = (
                f"USER REQUEST: {prompt}\n\n"
                "Think first inside <think> tags, then output the 3 code blocks. "
                "Return the component using exactly three markdown blocks: "
                "```typescript, ```html, and ```css. Do not output XML patches."
            )
        try:
            for event in agent.generate_events(final_prompt, cancel_event=cancel_event, thinking_enabled=request.thinking_enabled, current_code=request.current_code):
                if event["type"] in {"done", "error", "cancelled"}:
                    session["history"].append({"role": "agent", "event": event, "at": time.time()})
                    save_sessions()
                if event["type"] == "done":
                    metrics["generation_success_total"] += 1
                    session["versions"].append({
                        "code": event["code"],
                        "metrics": event.get("metrics", {}),
                        "at": time.time(),
                    })
                    save_sessions()
                if event["type"] == "error":
                    metrics["generation_error_total"] += 1
                    metrics["validation_error_total"] += len(event.get("errors", []))
                if event["type"] == "cancelled":
                    metrics["generation_cancelled_total"] += 1
                yield sse_event(event)
        finally:
            active_requests.pop(request.session_id, None)

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

@app.post("/async-generate")
async def async_generate(request: GenerateRequest, fastapi_request: Request):
    """
    Scalable endpoint designed for Kubernetes. Pushes the job to Redis and 
    streams tokens back as the ML Worker Pods process them in the background.
    """
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis queue is not configured or available.")

    prompt = request.prompt
    # Execute Guardrails Firewall (Same as synchronous endpoint)
    if guards and not request.current_code:
        for guard in guards:
            try:
                outcome = guard.validate(prompt)
                print(f"GUARDRAILS OUTCOME: {outcome}", flush=True)
                if hasattr(outcome, "validation_passed") and outcome.validation_passed is False:
                    raise ValueError("Guardrails validation failed")
            except Exception as e:
                error_str = str(e)
                print(f"GUARDRAILS EXCEPTION: {error_str}", flush=True)
                if "Missing credentials" in error_str or "litellm" in error_str:
                    pass 
                metrics["generation_failures"] += 1
                raise HTTPException(status_code=403, detail="Security Error: Prompt Injection or Toxic Language detected by Guardrails AI.")

    request_id = str(uuid.uuid4())
    job_payload = {
        "request_id": request_id,
        "prompt": prompt,
        "current_code": request.current_code
    }
    
    # Push job to Redis queue
    redis_client.lpush(REQUEST_QUEUE, json.dumps(job_payload))
    print(f"[API Gateway] Pushed job {request_id} to Redis queue.")

    async def redis_stream_generator():
        result_key = f"{RESULT_PREFIX}{request_id}"
        print(f"[API Gateway] Listening for results on {result_key}...")
        
        # Poll Redis for chunks from the worker
        while True:
            # BLPOP blocks until a chunk is available
            item = redis_client.blpop(result_key, timeout=30)
            if item is None:
                yield f"data: {json.dumps({'error': 'Worker timeout. Queue might be full or worker crashed.'})}\n\n"
                break
                
            _, raw_data = item
            data = json.loads(raw_data)
            
            if data["type"] == "done":
                break
            elif data["type"] == "error":
                yield f"data: {json.dumps({'error': data['content']})}\n\n"
                break
            elif data["type"] == "chunk":
                yield f"data: {json.dumps({'chunk': data['content']})}\n\n"
            
            # Small sleep to prevent tight loop CPU pinning
            await asyncio.sleep(0.01)

    return StreamingResponse(redis_stream_generator(), media_type="text/event-stream")

@app.post("/sessions/{session_id}/cancel")
def cancel_generation(session_id: str):
    cancel_event = active_requests.get(session_id)
    if not cancel_event:
        return {"cancelled": False, "reason": "No active generation for session."}
    cancel_event.set()
    return {"cancelled": True}

@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    return sessions.get(session_id, {"session_id": session_id, "history": [], "versions": []})

@app.get("/sessions/{session_id}/logs")
def get_session_logs(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "session_id": session_id,
        "history": session.get("history", []),
        "validation_logs": session.get("validation_logs", []),
        "preview_logs": session.get("preview_logs", []),
        "branches": session.get("branches", []),
    }

@app.get("/sessions/{session_id}/versions")
def list_versions(session_id: str):
    session = sessions.get(session_id, {"versions": []})
    return {
        "session_id": session_id,
        "versions": [
            {
                "index": index,
                "at": version.get("at"),
                "metrics": version.get("metrics", {}),
            }
            for index, version in enumerate(session.get("versions", []))
        ],
    }

@app.get("/sessions/{session_id}/versions/{version_index}")
def get_version(session_id: str, version_index: int):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    versions = session.get("versions", [])
    if version_index < 0 or version_index >= len(versions):
        raise HTTPException(status_code=404, detail="Version not found.")
    version = versions[version_index]
    return {
        "session_id": session_id,
        "index": version_index,
        "at": version.get("at"),
        "metrics": version.get("metrics", {}),
        "code": version.get("code", ""),
        "code_blocks": _extract_code_blocks(version.get("code", "")),
    }

@app.get("/sessions/{session_id}/versions/{from_index}/diff/{to_index}")
def diff_versions(session_id: str, from_index: int, to_index: int):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    versions = session.get("versions", [])
    for index in (from_index, to_index):
        if index < 0 or index >= len(versions):
            raise HTTPException(status_code=404, detail=f"Version {index} not found.")

    from_code = versions[from_index].get("code", "").splitlines(keepends=True)
    to_code = versions[to_index].get("code", "").splitlines(keepends=True)
    diff = difflib.unified_diff(
        from_code,
        to_code,
        fromfile=f"version-{from_index}",
        tofile=f"version-{to_index}",
    )
    return {
        "session_id": session_id,
        "from": from_index,
        "to": to_index,
        "diff": "".join(diff),
    }

@app.post("/sessions/{session_id}/snapshots")
def create_snapshot(session_id: str, request: SnapshotRequest):
    session = sessions.setdefault(session_id, {
        "session_id": session_id,
        "history": [],
        "versions": [],
        "branches": [],
        "created_at": time.time(),
    })
    code = _blocks_to_markdown(request.code_blocks)
    snapshot = {
        "name": request.name,
        "note": request.note,
        "code": code,
        "code_blocks": request.code_blocks,
        "at": time.time(),
    }
    session.setdefault("branches", []).append(snapshot)
    metrics["snapshot_total"] += 1
    save_sessions()
    return {"ok": True, "snapshot_index": len(session["branches"]) - 1, "snapshot": snapshot}

@app.get("/sessions/{session_id}/snapshots")
def list_snapshots(session_id: str):
    session = sessions.get(session_id, {"branches": []})
    return {
        "session_id": session_id,
        "snapshots": [
            {
                "index": index,
                "name": snapshot.get("name"),
                "note": snapshot.get("note"),
                "at": snapshot.get("at"),
            }
            for index, snapshot in enumerate(session.get("branches", []))
        ],
    }

@app.post("/sessions/{session_id}/snapshots/{snapshot_index}/restore")
def restore_snapshot(session_id: str, snapshot_index: int):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    snapshots = session.get("branches", [])
    if snapshot_index < 0 or snapshot_index >= len(snapshots):
        raise HTTPException(status_code=404, detail="Snapshot not found.")

    code_blocks = snapshots[snapshot_index].get("code_blocks") or _extract_code_blocks(snapshots[snapshot_index].get("code", ""))
    publish_preview(session_id, PreviewPublishRequest(code_blocks=code_blocks))
    session["restored_snapshot"] = snapshot_index
    session["last_restore_at"] = time.time()
    metrics["version_restore_total"] += 1
    save_sessions()
    return {"ok": True, "restored_snapshot": snapshot_index, "code_blocks": code_blocks}

@app.post("/sessions/{session_id}/versions/{version_index}/restore")
def restore_version(session_id: str, version_index: int):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    versions = session.get("versions", [])
    if version_index < 0 or version_index >= len(versions):
        raise HTTPException(status_code=404, detail="Version not found.")

    code_blocks = _extract_code_blocks(versions[version_index].get("code", ""))
    publish_preview(session_id, PreviewPublishRequest(code_blocks=code_blocks))
    session["restored_version"] = version_index
    session["last_restore_at"] = time.time()
    metrics["version_restore_total"] += 1
    save_sessions()
    return {"ok": True, "restored_version": version_index, "code_blocks": code_blocks}

@app.post("/sessions/{session_id}/preview")
def publish_preview(session_id: str, request: PreviewPublishRequest):
    blocks = {block.get("language"): block.get("code", "") for block in request.code_blocks}
    ts_code = blocks.get("typescript", "")
    html_code = blocks.get("html", "")
    css_code = blocks.get("css", "")
    if not ts_code or not html_code or not css_code:
        raise HTTPException(status_code=400, detail="typescript, html, and css blocks are required.")

    validation_markdown = f"```typescript\n{ts_code}\n```\n```html\n{html_code}\n```\n```css\n{css_code}\n```"
    validation_errors = app.state.validator.validate(validation_markdown)
    session = sessions.setdefault(session_id, {"session_id": session_id, "history": [], "versions": [], "created_at": time.time()})
    session.setdefault("validation_logs", []).append({
        "at": time.time(),
        "ok": not bool(validation_errors),
        "errors": validation_errors,
    })
    if validation_errors:
        metrics["preview_publish_error_total"] += 1
        save_sessions()
        raise HTTPException(status_code=422, detail=" | ".join(validation_errors))

    frontend_dir = Path(__file__).resolve().parents[1] / "frontend" / "src" / "app" / "generated-preview"
    frontend_dir.mkdir(parents=True, exist_ok=True)
    files = {
        frontend_dir / "generated.component.ts": _normalize_generated_ts(ts_code),
        frontend_dir / "generated.component.html": html_code,
        frontend_dir / "generated.component.css": fix_css_variables(css_code),
    }
    workspace_dir = _preview_workspace_dir(session_id)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    workspace_files = {
        workspace_dir / "generated.component.ts": files[frontend_dir / "generated.component.ts"],
        workspace_dir / "generated.component.html": html_code,
        workspace_dir / "generated.component.css": css_code,
    }
    previous = {path: path.read_text(encoding="utf-8") if path.exists() else "" for path in files}
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
    for path, content in workspace_files.items():
        path.write_text(content, encoding="utf-8")

    compile_result = _validate_preview_compile()
    if not compile_result["ok"]:
        for path, content in previous.items():
            path.write_text(content, encoding="utf-8")
        metrics["preview_publish_error_total"] += 1
        session.setdefault("preview_logs", []).append({
            "at": time.time(),
            "ok": False,
            "compile": compile_result,
            "workspace": str(workspace_dir),
        })
        save_sessions()
        raise HTTPException(status_code=422, detail=compile_result["error"])

    session["last_preview_at"] = time.time()
    session["last_preview_workspace"] = str(workspace_dir)
    session.setdefault("preview_logs", []).append({
        "at": time.time(),
        "ok": True,
        "compile": compile_result,
        "workspace": str(workspace_dir),
    })
    metrics["preview_publish_total"] += 1
    save_sessions()
    return {"ok": True, "preview_path": "/preview", "workspace": str(workspace_dir), "compile": compile_result}

def _normalize_generated_ts(ts_code: str) -> str:
    return normalize_ts_code(ts_code, "")

def _extract_code_blocks(markdown: str) -> list[dict[str, str]]:
    blocks = []
    for language, code in re.findall(r"```(\w+)\s*\n(.*?)```", markdown, flags=re.DOTALL):
        normalized = "typescript" if language == "ts" else language
        blocks.append({"language": normalized, "code": code.strip()})
    return blocks

def _blocks_to_markdown(code_blocks: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"```{block.get('language', 'raw')}\n{block.get('code', '')}\n```"
        for block in code_blocks
    )

def _preview_workspace_dir(session_id: str) -> Path:
    safe_session_id = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)[:120]
    return Path(__file__).resolve().parent / "runtime" / "preview-workspaces" / safe_session_id

def _validate_preview_compile() -> dict:
    if os.getenv("PREVIEW_COMPILE_VALIDATE", "true").lower() != "true":
        return {"ok": True, "skipped": True}

    project_root = Path(__file__).resolve().parents[1]
    mode = os.getenv("PREVIEW_COMPILE_MODE", "tsc").lower()
    timeout = int(os.getenv("PREVIEW_COMPILE_TIMEOUT_SECONDS", "20"))
    if mode == "build":
        command = ["npm", "run", "build"]
    else:
        tsc_bin = project_root / "frontend" / "node_modules" / ".bin" / "tsc"
        if not tsc_bin.exists():
            return {"ok": True, "skipped": True, "reason": "TypeScript compiler not installed."}
        command = [str(tsc_bin), "-p", str(project_root / "frontend" / "tsconfig.app.json"), "--noEmit"]

    try:
        result = subprocess.run(
            command,
            cwd=project_root / "frontend",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return {"ok": True}
        return {
            "ok": False,
            "error": (result.stdout + "\n" + result.stderr).strip() or "Preview compile validation failed.",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Preview compile validation timed out after {timeout} seconds."}
    except Exception as e:
        return {"ok": False, "error": f"Preview compile validation failed: {str(e)}"}

@app.get("/design-system")
def get_design_system(request: Request):
    json_path = request.app.state.design_system_path
    try:
        with open(json_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"error": "design-system.json not found"}

@app.get("/health")
def health(request: Request):
    generation_provider = request.app.state.generation_provider
    return {
        "ok": bool(request.app.state.generator and request.app.state.validator),
        "model_loaded": bool(request.app.state.generator),
        "generator_loaded": bool(request.app.state.generator),
        "local_model_loaded": generation_provider == "llama" and bool(request.app.state.generator),
        "validator_loaded": bool(request.app.state.validator),
        "agent_loaded": bool(request.app.state.agent),
        "generation_provider": generation_provider,
        "model_error": request.app.state.model_error,
    }

@app.get("/metrics")
def prometheus_metrics(request: Request):
    lines = []
    for name, value in metrics.items():
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {value}")
    lines.append("# TYPE active_generations gauge")
    lines.append(f"active_generations {len(active_requests)}")
    lines.append("# TYPE backend_model_loaded gauge")
    lines.append(f"backend_model_loaded {1 if request.app.state.generator else 0}")
    return Response("\n".join(lines) + "\n", media_type="text/plain")
