# Change: bootstrap-finance-ticket-agent-mvp

## Why

This project needs a clear contract for a focused financial ticket Agent instead of drifting into a generic chatbot or an oversized finance platform.

This bootstrap change defines the project scope before implementation so later phases can be checked against OpenSpec.

## What Changes

- Initialize a repository-level OpenSpec change for the MVP.
- Define architecture and boundaries for React + TypeScript, Python/FastAPI, LangGraph, MCP-style Tool Registry, Go account transaction HTTP API, PostgreSQL, Redis, RAG, trace, and evaluation.
- Define acceptance requirements for three representative financial ticket tasks:
  - reimbursement policy Q&A
  - balance anomaly explanation
  - reconciliation anomaly localization
- Create Chinese README and docs skeletons.
- Create engineering notes that record design decisions, implementation boundaries, and validation evidence.

## Out of Scope

- No production payment, clearing, settlement, risk-control, or audit system claims.
- No business scenarios beyond the three supported ticket types.
- No full MCP server in the first version; only a MCP-style tool definition layer.
- No direct Agent access to the Go service PostgreSQL database.
- No modification of `D:\Career_Research\go-account-transaction` in this change.
- No complex multi-agent architecture, Kafka, Kubernetes, or distributed workflow.
