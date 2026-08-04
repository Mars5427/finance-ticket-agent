# Design: Finance Ticket Agent MVP

## Project Scope

Project name: 面向财务场景的智能工单处理 Agent

Required stack: Python, FastAPI, LangGraph, React, TypeScript, Go, PostgreSQL, Redis, RAG, Tool Calling, Docker, OpenSpec.

The implementation maps to five feature goals:
1. Agent Workflow for three financial ticket tasks.
2. Python/FastAPI + LangGraph Agent service with state, context, tool history, structured output, and MCP-style tool registry.
3. Go account transaction service reused as the business data backend through Tool Calling APIs.
4. Finance rules knowledge base with RAG snippets in answers.
5. Trace and frontend workbench with ticket list, execution steps, tool parameters/results, latency, failure reason, conclusion, and evaluation cases.

## Architecture

```text
React + TypeScript 前端工单工作台
        ↓
Python FastAPI Agent API
        ↓
LangGraph Agent Workflow
        ↓
MCP 风格 Tool Registry
        ↓
Go 账户交易系统 HTTP API
        ↓
PostgreSQL / Redis
```

## Boundary With Go Account Service

The Agent will never connect to PostgreSQL directly. It calls business tools, and those tools call the Go HTTP API.

Reasons:
- The Go service owns transaction, ledger, validation, idempotency, and Redis rate-limit boundaries.
- Tool Calling gives the Agent a narrow, auditable capability surface.
- HTTP API responses are safer to expose to the Agent than raw database tables.
- The tool layer can log parameters, outputs, latency, and failures for trace and engineering evidence.

Phase 2 tools:
- `get_account`: wraps `GET /v1/accounts/{id}`.
- `list_account_transactions`: wraps `GET /v1/accounts/{id}/transactions`.
- `get_transaction_detail`: wraps `GET /v1/transfers/{id}`.
- `check_account_reconciliation`: wraps `GET /v1/accounts/{id}/reconciliation`.

Phase 2 is limited to Tool Registry, Go HTTP client integration, and tool call trace. It does not introduce LangGraph, real RAG retrieval, or a full MCP Server.

Reconciliation tickets use two layers of judgment:
- Go internal consistency: compare `current_balance` with `latest_ledger_balance_after` through `check_account_reconciliation`.
- External expectation consistency: compare Go `current_balance` with user-provided `metadata.expected_balance`.

If Go internal consistency is matched but the external expected balance differs, the ticket is still escalated because the likely issue is outside the internal ledger, such as statement source, time range, or posting delay. If `expected_balance` cannot be parsed as an integer, the workflow escalates with a format explanation instead of crashing.

## Agent State Machine

Phase 3 replaces the deterministic orchestration shell with a LangGraph workflow using explicit states:
- `received`: ticket accepted.
- `classified`: ticket type identified as reimbursement Q&A, balance anomaly, reconciliation anomaly, or unsupported.
- `needs_more_info`: required fields are missing and a follow-up question is generated.
- `planned`: task decomposition and selected tools are recorded.
- `tool_running`: a registered tool is being executed.
- `rag_running`: finance knowledge retrieval is being executed.
- `summarizing`: structured result is being assembled.
- `escalated`: human escalation is required.
- `completed`: final result is produced.
- `failed`: unrecoverable execution failure is recorded.

LangGraph nodes:
- `initialize_context`: builds title, description, metadata, ticket id, dialogue context, tool history, trace, and timing context.
- `classify`: classifies into the three supported ticket types or unsupported.
- `check_missing_fields`: validates required metadata and generates follow-up questions.
- `plan`: records task decomposition and candidate tools.
- `retrieve_evidence`: retrieves Markdown RAG evidence for reimbursement rules and SOP support.
- `execute_tools`: invokes the existing Tool Registry only.
- `summarize`: assembles summary, retrieved evidence, and tool call records.
- `escalation_check`: applies missing-evidence, tool-failure, balance-difference, expected-balance mismatch, and unsupported checks.
- `finalize`: returns the existing `TicketResponse` shape.

Phase 4.5 continuation:
- Adds `TicketContinueRequest` with `message` and `metadata_patch`.
- Adds `POST /api/tickets/{ticket_id}/continue`.
- Continuation is limited to same-ticket missing-parameter follow-up.
- The API loads the existing ticket, merges metadata, preserves title/description/id, appends the message to single-ticket `dialogue_context`, keeps old trace, appends continuation trace events, and re-runs LangGraph.
- This is lightweight task-state continuation, not general chat, long-term memory, or cross-ticket memory.

## Ticket Types

1. Reimbursement policy Q&A
   - Inputs: question, optional employee level, expense type, amount, city, date.
   - Main path: classify -> retrieve policy/SOP snippets -> structured answer with citations -> escalation if rules conflict or evidence is weak.

2. Balance anomaly explanation
   - Inputs: account id, observed balance, optional time range and user description.
   - Main path: classify -> validate required account id/observed balance -> get account -> list transactions -> explain likely difference -> escalation if data is missing or inconsistent.

3. Reconciliation anomaly localization
   - Inputs: account id, expected balance or statement amount, time range, optional transaction id.
   - Main path: classify -> gather ledger/transaction evidence -> run reconciliation check -> identify mismatch candidates -> escalation if mismatch cannot be localized.

## Tool Registry

Each tool definition must contain:
- `name`
- `description`
- `input_schema`
- `output_schema`
- `handler`
- error mapping

This is "可 MCP 化" because the metadata can later be exposed through a MCP server without changing the Agent workflow contract.

## RAG

Phase 4 implements lightweight Markdown RAG over files under `knowledge/`:
- `reimbursement-policy.md`
- `approval-rules.md`
- `reconciliation-sop.md`

The first implementation uses local chunking plus keyword/BM25-like scoring, not a vector database. Answers must return evidence snippets with `source`, `heading`, `snippet`, and `score`. The goal is to reduce hallucination risk, not to claim legal or production finance correctness.

RAG ingestion:
- Split Markdown by headings and paragraphs.
- Store `source`, `heading`, `content`, and `chunk_id` for each chunk.
- Do not hard-code answers; retrieval must score actual chunks.

RAG behavior by ticket type:
- Reimbursement policy Q&A retrieves reimbursement policy and approval rules and requires evidence snippets.
- Reconciliation anomaly retrieves reconciliation SOP to explain manual review recommendations.
- Balance anomaly may retrieve exception-handling SOP; if no strong match exists, it should not invent evidence.

The LangGraph workflow adds a `retrieve_evidence` node. The node records a `rag_retrieval` trace event with query, matched sources, snippets, scores, elapsed ms, and no-evidence reason.

Phase 4 boundaries:
- No vector database.
- No LLM call.
- No full MCP Server.
- No complete multi-turn chat; Phase 4.5 only supports same-ticket missing-parameter continuation.

## Trace

Trace events must capture:
- ticket creation and classification
- missing parameter checks
- plan/task decomposition
- selected tools
- tool parameters
- tool return payload or error
- RAG query and evidence snippets
- elapsed time
- failure reason
- final status and escalation decision

## Data Model

Initial FastAPI-side models:
- `Ticket`: id, title, description, type, status, required fields, context, final result, escalation reason, created/updated timestamps.
- `TicketContinueRequest`: message and metadata_patch for same-ticket missing-parameter continuation.
- `TraceEvent`: id, ticket id, step, event type, payload, elapsed ms, error, created timestamp.
- `ToolCallRecord`: id, ticket id, tool name, parameters, result, status, elapsed ms, error.
- `KnowledgeSnippet`: source, heading, text, score.

Storage may start in memory or SQLite for Phase 1, then move to PostgreSQL when the phase requires persistence. The Go service remains the source of truth for account/transaction data.

## Frontend Workbench

The React workbench must show:
- ticket list
- ticket detail
- current status
- execution steps
- tool parameters and returns
- elapsed time
- failure reason
- final conclusion
- human escalation marker
- continuation form for `needs_more_info` tickets, with message and metadata_patch JSON inputs

## Evaluation

Evaluation cases live in `eval_cases/finance_tickets.json`. Metrics:
- task completion rate
- status match rate
- average tool call count
- human escalation ratio
- RAG evidence coverage
- continuation success rate
- failure type distribution

Phase 5 evaluation is offline and deterministic:
- It loads at least 10 fixed cases from `eval_cases/finance_tickets.json`.
- It uses an injected fake tool registry instead of the real Go service.
- It runs the same LangGraph workflow used by the Agent API.
- It supports cases with an optional same-ticket continuation request.
- It writes an eval summary that can be used as engineering evidence.

Failure type distribution uses stable categories:
- `no_evidence`
- `tool_failure`
- `missing_parameters`
- `expected_balance_mismatch`
- `internal_reconciliation_mismatch`
- `invalid_expected_balance`
- `unsupported_scope`
- `status_mismatch`
- `type_mismatch`

The metrics are fixed-case validation for local engineering and quality regression. They are not production accuracy, online quality, LLM quality, or business correctness claims. No metric may be claimed until the evaluation script is implemented and run.

## Phase 6.5 Optional LLM Summary Node

Phase 6.5 adds an optional LLM refinement node after deterministic `summarize` and before `escalation_check`.

The node is deliberately narrow:
- Classification remains deterministic.
- Tool Calling remains routed through the existing MCP-style Tool Registry.
- RAG remains local Markdown retrieval.
- The deterministic summary is always generated first.
- LLM output can refine the human-readable summary but cannot rewrite tool calls, evidence, ticket type, metadata, or classification.

Configuration:
- `LLM_ENABLED`: `true` or `false`; default is false.
- `LLM_PROVIDER`: `openai`, `deepseek`, or `disabled`; default is disabled.
- `LLM_API_KEY`: API key; never written to docs, trace, or evidence.
- `LLM_MODEL`: chat model name.
- `LLM_BASE_URL`: OpenAI-compatible base URL.
- `LLM_TIMEOUT_SECONDS`: HTTP timeout.
- `LLM_MAX_TOKENS`: optional output budget, default 800.

DeepSeek smoke alignment uses provider `deepseek`, model `deepseek-v4-flash`, base URL `https://api.deepseek.com`, path `/chat/completions`, `response_format={"type":"json_object"}`, and a 20-second timeout example.

Implementation approach:
- Use OpenAI-compatible Chat Completions over HTTP instead of binding to a vendor SDK.
- Prompt version is `finance_ticket_summary_v1`.
- Prompt inputs include ticket type, title, description, metadata, deterministic summary, evidence snippets, tool calls, needs_human, and escalation reason.
- Prompt requires JSON output: `summary`, `needs_human`, `escalation_reason`, and `confidence`.
- Prompt includes a concrete JSON output example so JSON Output providers have an explicit schema-like target.

Fallback and trace:
- Disabled or missing key records `llm_skipped` and keeps deterministic output.
- HTTP failure, invalid JSON, or missing fields records `llm_fallback` and keeps deterministic output.
- Successful calls record `llm_call` with provider, model, prompt version, elapsed ms, and summary lengths only.
- If deterministic logic already requires human review, the LLM cannot downgrade `needs_human=true` to false.

Phase 6.5 still does not add a full MCP Server, vector database, new ticket types, complete chat, long-term memory, cross-ticket memory, or Go repository changes.

## Known Constraints

- We do not modify the original Go account transaction repository without explicit user approval.
- We do not claim a full MCP server in v1.
- We do not expand beyond three ticket types.
- We keep OpenSpec artifacts updated before behavior changes.

## Phase 6 Final Handoff

Phase 6 is documentation, evidence, and engineering handoff closure only. It does not add large product capabilities.

Final handoff must include:
- A feature-goal alignment table in README, design docs, and engineering notes.
- Startup and demo instructions for FastAPI, React, Go-service dependency, and offline eval.
- API examples for ticket creation, same-ticket continuation, list/detail/trace, tools, and eval CLI.
- Evidence index from Phase 1 through Phase 6.
- Clear limitations: optional LLM summary only with deterministic fallback by default, no vector database, no complete MCP Server, no generic multi-turn chat, no long-term or cross-ticket memory, no online accuracy claims, and only three supported ticket types.
- Engineering notes and Q&A explaining Tool Calling, LangGraph, RAG, trace, human escalation, Go service boundary, evaluation metrics, and CRUD differences.
