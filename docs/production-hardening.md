# Production Hardening Notes

This repository now implements the end-to-end local demo path, but these are the next steps for true multi-user production.

## Preview Isolation

Current behavior:

- Generated code is copied into a per-session backend workspace under `backend/runtime/preview-workspaces/{session_id}`.
- The active preview is also written to one shared Angular preview component for local development.
- `/preview` renders that shared component.

Production behavior:

- Create a per-session preview workspace.
- Compile generated code in an isolated worker/container.
- Serve each preview through a unique route or ephemeral preview deployment.
- Keep generated files outside the main frontend source tree.

Suggested approaches:

- Kubernetes job per preview build.
- Pool of preview workers with per-session directories.
- Server-side artifact store for compiled preview bundles.
- Browser sandbox such as WebContainers if fully client-side preview is desired.

## Inference Scaling

Current behavior:

- One local `llama.cpp` model instance is loaded in the backend.
- Access is serialized with a lock to avoid native crashes.
- Kubernetes includes an inference-worker deployment shape and Redis queue manifests.

Production behavior:

- Move generation execution from the API process into the inference worker.
- Queue generation jobs through Redis or a managed queue.
- Scale inference workers independently.
- Pin GPU workers to GPU node pools.
- Keep a warm model pool to reduce cold starts.

## Validation

Current behavior:

- Static validator plus TypeScript preview compile.
- Optional `PREVIEW_COMPILE_MODE=build` for Angular production build validation.
- Template checks catch missing event handlers, missing referenced members, and missing Angular modules for common directives.

Production behavior:

- Add Angular production build validation.
- Add ESLint rules for generated TypeScript/HTML/CSS.
- Capture compiler diagnostics as structured validation errors.

## Observability

Current behavior:

- `/metrics` exposes basic Prometheus counters/gauges.
- K8s includes Prometheus, Grafana, and OpenTelemetry Collector manifests.

Production behavior:

- Instrument the Python backend with OpenTelemetry spans around generation, validation, preview publish, and compile.
- Dashboard first-token latency, total generation latency, retry count, validation failures, active generation count, and provider/model.
