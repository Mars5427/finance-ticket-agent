# finance-ticket-agent-mvp Specification Delta

## ADDED Requirements

### Requirement: Containerized Agent runtime

The system SHALL provide a containerized runtime for the FastAPI Agent API and the React frontend workbench.

#### Scenario: Agent API image build
- **WHEN** the repository builds the `agent-api` image
- **THEN** the image contains the FastAPI runtime code and required Markdown knowledge files
- **AND** it starts the API with `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`

#### Scenario: Frontend image build
- **WHEN** the repository builds the `frontend` image
- **THEN** the image serves the production React build as static files
- **AND** `/api` and `/healthz` are proxied to the `agent-api` service

#### Scenario: Compose topology
- **WHEN** `docker compose config` is run from the repository root
- **THEN** the compose file defines `agent-api` and `frontend`
- **AND** it does not define Agent-side PostgreSQL or Redis services

#### Scenario: External Go service dependency
- **WHEN** the Agent API runs in Docker
- **THEN** it reads `GO_ACCOUNT_API_BASE_URL`
- **AND** the default value can be `http://host.docker.internal:8080`
- **AND** documentation states that the Go account transaction service must be started separately or exposed externally

#### Scenario: Optional LLM runtime configuration
- **WHEN** the Agent API runs in Docker
- **THEN** compose passes `LLM_ENABLED`, `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT_SECONDS`, and `LLM_MAX_TOKENS`
- **AND** their defaults keep LLM disabled when no key is configured

#### Scenario: Frontend API access in Docker
- **WHEN** the Dockerized frontend is opened in a browser
- **THEN** frontend requests to `/api` reach the `agent-api` container through the frontend proxy
- **AND** the API does not require browser-side absolute backend URLs

### Requirement: Optional LLM metadata extraction boundary

If implemented, LLM-based metadata extraction SHALL remain a default-off enhancement and must not weaken deterministic business controls.

#### Scenario: Extraction fills only missing metadata
- **WHEN** the metadata extraction node runs
- **THEN** it may fill candidate metadata fields that are currently missing
- **AND** it does not overwrite explicit user-provided metadata

#### Scenario: Extraction does not replace business control
- **WHEN** metadata extraction succeeds or fails
- **THEN** it does not change ticket type, tool calls, evidence, or escalation rules
- **AND** low-confidence or invalid extraction still falls back to normal missing-parameter follow-up

#### Scenario: Extraction trace safety
- **WHEN** metadata extraction is skipped, succeeds, or falls back
- **THEN** trace records a non-sensitive extraction event
- **AND** trace does not include API keys, authorization headers, or full prompts
