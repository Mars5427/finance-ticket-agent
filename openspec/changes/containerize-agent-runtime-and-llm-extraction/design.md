# Design: Containerized Agent Runtime and Optional LLM Metadata Extraction

## Scope

This change focuses on delivery and reproducibility rather than new business capabilities.

Primary goals:
1. Containerize `agent-api`.
2. Containerize `frontend`.
3. Provide a real two-service `docker-compose.yml`.
4. Preserve existing local startup and offline evaluation paths.

Optional goal:
- Add a narrowly scoped LLM metadata extraction node only if it can be kept default-off, deterministic-safe, and low-risk.

## Runtime Architecture

```text
Browser
  -> frontend container (Nginx, static React build)
      -> /api, /healthz proxied to agent-api container
          -> FastAPI + LangGraph + Tool Registry + Markdown RAG
              -> external Go account transaction HTTP API
```

The compose stack is intentionally small:
- `agent-api`
- `frontend`

It does not own:
- the Go account transaction service
- the Go service PostgreSQL
- the Go service Redis

## Agent API Container

Container requirements:
- base image: Python 3.11 slim or equivalent
- install runtime dependencies only
- run `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- include `app/`, `scripts/`, and repository knowledge files required by Markdown RAG
- exclude `.venv`, `__pycache__`, test caches, and local artifacts

The API must continue reading:
- `GO_ACCOUNT_API_BASE_URL`
- `LLM_ENABLED`
- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_BASE_URL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_TOKENS`

Safe defaults keep LLM disabled.

## Frontend Container

Container requirements:
- multi-stage build
- Node stage runs `npm ci` and `npm run build`
- Nginx stage serves `dist`
- Nginx proxies `/api` and `/healthz` to `http://agent-api:8000`
- frontend routes fall back to `index.html`

This separates local development behavior from container runtime behavior:
- local development keeps Vite dev proxy
- container runtime uses Nginx reverse proxy

## Compose Design

Compose defaults:
- API host port: `8000`
- frontend host port: `5173`
- Go API default base URL: `http://host.docker.internal:8080`

The compose file must not contain real secrets.

Example runtime variables:
- `GO_ACCOUNT_API_BASE_URL=${GO_ACCOUNT_API_BASE_URL:-http://host.docker.internal:8080}`
- `LLM_ENABLED=${LLM_ENABLED:-false}`
- `LLM_PROVIDER=${LLM_PROVIDER:-disabled}`
- `LLM_API_KEY=${LLM_API_KEY:-}`
- `LLM_MODEL=${LLM_MODEL:-}`
- `LLM_BASE_URL=${LLM_BASE_URL:-}`
- `LLM_TIMEOUT_SECONDS=${LLM_TIMEOUT_SECONDS:-10}`
- `LLM_MAX_TOKENS=${LLM_MAX_TOKENS:-800}`

## Go Service Boundary

The Agent runtime continues to call the Go service over HTTP only.

Reasons:
- business validation and reconciliation semantics stay in the Go service
- the Agent remains auditable through Tool Calling and trace
- the Dockerized Agent runtime stays independent from the Go data plane

Documentation must explicitly state that the Go service must be started separately or exposed through a reachable external URL.

## Optional LLM Metadata Extraction

This change may add a metadata extraction node only if it remains narrow and low-risk.

If implemented, it must:
- be controlled by `LLM_METADATA_EXTRACTION_ENABLED=false` by default
- run after `classify` and before `check_missing_fields`
- only fill missing metadata fields
- never overwrite explicit user metadata
- never change ticket type, tool calls, evidence, or escalation rules
- never replace missing-parameter follow-up when confidence is low

Allowed candidate fields:
- `account_id`
- `observed_balance`
- `expected_balance`
- `time_range`
- `expense_type`
- `amount`
- `city`
- `date`

Trace events must be non-sensitive:
- `llm_metadata_extraction_skipped`
- `llm_metadata_extraction`
- `llm_metadata_extraction_fallback`

If the implementation introduces material complexity or regression risk, it should be deferred and documented as a future iteration instead of being shipped in this change.

## Documentation Impact

The repository documentation must explain:
- how to run the project without Docker
- how to run the project with Docker
- why only the Agent runtime is containerized here
- why the Go service remains external
- that Agent API state is still in memory
- that LLM remains optional and disabled by default

The repository documentation should describe the project as an independent engineering system with clear runtime and validation boundaries.
