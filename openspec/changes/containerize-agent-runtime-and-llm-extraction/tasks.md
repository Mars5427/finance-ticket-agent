# Tasks: containerize-agent-runtime-and-llm-extraction

## OpenSpec

- [x] 1.1 Create proposal, design, tasks, and specs for containerized runtime delivery.
- [x] 1.2 Validate the new OpenSpec change with `openspec validate --all --strict`.

## Agent API container

- [x] 2.1 Add `agent-api/Dockerfile`.
- [x] 2.2 Add API build ignore rules or equivalent packaging cleanup.
- [x] 2.3 Ensure the container includes runtime code and Markdown knowledge files required by RAG.

## Frontend container

- [x] 3.1 Add `frontend/Dockerfile`.
- [x] 3.2 Add `frontend/nginx.conf` for static hosting and API proxying.
- [x] 3.3 Add frontend build ignore rules if needed.

## Compose

- [x] 4.1 Replace the compose placeholder with `agent-api` and `frontend` services.
- [x] 4.2 Pass Go API and optional LLM environment variables with safe defaults.
- [x] 4.3 Keep the stack limited to the Agent runtime and avoid adding PostgreSQL or Redis services.

## Optional LLM metadata extraction

- [x] 5.1 Decide whether metadata extraction is low-risk enough for this change.
- [x] 5.2 If not implemented, document it as a deferred iteration.

## Docs and evidence

- [x] 6.1 Update README and repository docs for bare-metal and Docker startup.
- [x] 6.2 Update API and workflow documentation for container routing and runtime boundaries.
- [x] 6.3 Update engineering notes and the external handbook with engineering-focused runtime guidance.
- [x] 6.4 Add Phase 7 Docker evidence entries under `docs/evidence/README.md`.

## Validation

- [x] 7.1 Run `python -m unittest discover -s tests -v`.
- [x] 7.2 Run `npm run build`.
- [x] 7.3 Run `openspec validate --all --strict`.
- [x] 7.4 Run `docker compose config`.
- [x] 7.5 Run `docker compose build`.
- [x] 7.6 Run `docker compose up -d` and perform API/frontend smoke tests.
- [x] 7.7 Run `docker compose down`.
- [x] 7.8 Save evidence under `docs/evidence/phase7-*`.

Blocked notes:
- `7.5` is complete after the required base images were pulled successfully on August 4, 2026.
- `7.6` was initially delayed by a host-side request encoding issue. The final smoke passed after sending the Chinese request body with JSON Unicode escapes, confirming the published API port returns the expected reimbursement workflow result.
