# Change: containerize-agent-runtime-and-llm-extraction

## Why

The repository already demonstrates a complete local workflow for a focused finance ticket Agent, but it still depends on readers manually reconstructing the runtime environment for Python, Node, and frontend-to-backend routing.

This change makes the project easier to reproduce, demo, and extend as an engineering repository by:
- packaging the FastAPI service into a runnable container
- packaging the React workbench into a static container with API proxying
- defining a real `docker-compose.yml` for the Agent runtime
- documenting the external Go account service dependency explicitly

An optional LLM metadata extraction node is considered in this change, but it is lower priority than containerization and should only be implemented if it does not destabilize the existing deterministic workflow.

## What Changes

- Add a Docker build and runtime path for `agent-api`.
- Add a Docker build and runtime path for `frontend`.
- Replace the root compose placeholder with a reproducible two-service setup.
- Pass Go API and optional LLM environment variables into the API container with safe defaults.
- Document bare-metal and Docker startup paths side by side.
- Clarify that the Go account transaction service must be started separately or provided as an external endpoint.
- Keep LLM behavior optional and disabled by default.
- Capture new engineering evidence for Docker build, compose config, and runtime smoke tests.

## Out of Scope

- No changes to `D:\Career_Research\go-account-transaction`.
- No Agent-side PostgreSQL or Redis container.
- No new financial ticket types.
- No full MCP Server.
- No vector database.
- No migration from in-memory Agent state to persistent storage.
- No requirement to implement LLM metadata extraction in this change if it adds risk.
