# Tasks: bootstrap-finance-ticket-agent-mvp

## Phase 0: 规格与骨架

- [x] 0.1 Confirm project scope and source material.
- [x] 0.2 Create `D:\finance-ticket-agent`.
- [x] 0.3 Initialize Git and OpenSpec.
- [x] 0.4 Create proposal, design, tasks, and specs for the MVP.
- [x] 0.5 Create repository instructions in `AGENTS.md`.
- [x] 0.6 Create Chinese README and docs skeletons.
- [x] 0.7 Create initial knowledge and evaluation sample files.
- [x] 0.8 Create and update engineering decision notes.
- [x] 0.9 Run `openspec validate --all --strict`.

## Phase 1: 无 LLM 的垂直闭环

- [x] 1.1 Update OpenSpec tasks/specs before implementation.
- [x] 1.2 Scaffold FastAPI ticket API.
- [x] 1.3 Implement deterministic workflow for the three ticket types.
- [x] 1.4 Persist ticket state and trace events in a simple local store.
- [x] 1.5 Scaffold React + TypeScript workbench.
- [x] 1.6 Display ticket list, ticket detail, and execution steps.
- [x] 1.7 Run available Python tests, frontend build, FastAPI smoke test, and OpenSpec validate.
- [x] 1.8 Update README, docs, API doc, and engineering notes.

## Phase 2: 工具注册层与 Go API 对接

- [x] 2.1 Update OpenSpec for MCP-style Tool Registry behavior.
- [x] 2.2 Implement tool metadata with name, description, input schema, output schema.
- [x] 2.3 Implement `get_account`.
- [x] 2.4 Implement `list_account_transactions`.
- [x] 2.5 Implement `get_transaction_detail`.
- [x] 2.6 Implement `check_account_reconciliation`.
- [x] 2.7 Add tool call trace records.
- [x] 2.8 Run Go API connectivity check and available tests.
- [x] 2.9 Update README, docs, API doc, and engineering notes.
- [x] 2.10 Include `metadata.expected_balance` in reconciliation anomaly judgment and document the two-layer reconciliation semantics.

## Phase 3: LangGraph Agent Workflow

- [x] 3.1 Update OpenSpec before replacing deterministic workflow behavior.
- [x] 3.2 Add LangGraph dependency and verify it imports in the local Python environment.
- [x] 3.3 Implement LangGraph nodes: initialize_context, classify, check_missing_fields, plan, execute_tools, summarize, escalation_check, finalize.
- [x] 3.4 Preserve external Agent API response compatibility.
- [x] 3.5 Maintain ticket state, dialogue context, tool history, trace, and structured output.
- [x] 3.6 Add tests for classification, missing-parameter follow-up, balance tool calls, reconciliation expected_balance mismatch, tool failure escalation, and unsupported escalation.
- [x] 3.7 Run Python tests, frontend build, OpenSpec validate, Docker Compose config, and FastAPI smoke when Go API is available.
- [x] 3.8 Update README, docs, API doc, and engineering notes.

## Phase 4: RAG

- [x] 4.1 Update OpenSpec for Markdown RAG behavior, trace, and no-evidence escalation.
- [x] 4.2 Implement Markdown knowledge ingestion with source, heading, content, and chunk_id.
- [x] 4.3 Implement lightweight keyword/BM25-like retrieval over reimbursement policy, approval rules, and reconciliation SOP.
- [x] 4.4 Add LangGraph `retrieve_evidence` node and RAG trace events.
- [x] 4.5 Use retrieved evidence in reimbursement, balance, and reconciliation summaries without fabricating unsupported answers.
- [x] 4.6 Add tests for reimbursement hits, no-evidence behavior, reconciliation SOP evidence, rag trace, and Phase 2/3 regressions.
- [x] 4.7 Run Python tests, frontend build, OpenSpec validate, Docker Compose config, and FastAPI smoke when Go API is available.
- [x] 4.8 Update README, docs, API doc, evidence README, and engineering notes.

## Phase 4.5: 多轮补参与 ticket continue

- [x] 4.5.1 Update OpenSpec before adding same-ticket continuation behavior.
- [x] 4.5.2 Add `TicketContinueRequest` with `message` and `metadata_patch`.
- [x] 4.5.3 Add `POST /api/tickets/{ticket_id}/continue` for same-ticket continuation.
- [x] 4.5.4 Merge metadata, preserve ticket id/title/description, append dialogue context, preserve old trace, and append continuation trace.
- [x] 4.5.5 Re-run LangGraph workflow for the same ticket and update result/status/tool_calls/evidence/updated_at.
- [x] 4.5.6 Add backend tests for successful continuation, trace/context preservation, missing ticket 404, invalid metadata_patch, and Phase 4 RAG regression.
- [x] 4.5.7 Update frontend to show a continuation form for `needs_more_info` tickets and refresh the same ticket.
- [x] 4.5.8 Run Python tests, frontend build, OpenSpec validate, Docker Compose config, and FastAPI smoke when Go API is available.
- [x] 4.5.9 Update README, docs, API doc, evidence README, and engineering notes.

## Phase 5: Trace 与评估

- [x] 5.1 Update OpenSpec for offline fixed-case evaluation metrics.
- [x] 5.2 Add 10+ fixed eval cases covering three ticket types, missing parameters, continuation, no evidence, tool failure, expected_balance mismatch, and unsupported scope.
- [x] 5.3 Implement an eval runner using an injected FakeRegistry so it does not depend on the real Go service.
- [x] 5.4 Compute total_cases, task_completion_rate, status_match_rate, average_tool_call_count, human_escalation_ratio, rag_evidence_coverage, continuation_success_rate, and failure_type_distribution.
- [x] 5.5 Add tests for eval case loading, metric calculation, continuation evaluation, and failure type distribution without regressing Phase 4/4.5 tests.
- [x] 5.6 Run Python tests, frontend build, OpenSpec validate, Docker Compose config, and save eval summary evidence.
- [x] 5.7 Update README, docs, API doc if needed, evidence README, and engineering notes.

## Phase 6: 验收与工程文档

- [x] 6.1 Update OpenSpec for final feature-goal alignment and evidence requirements before documentation changes.
- [x] 6.2 Add a feature-goal alignment table to README, design doc, and engineering notes.
- [x] 6.3 Complete README with positioning, stack, architecture, startup commands, API examples, frontend demo path, eval command, evidence index, and limitations.
- [x] 6.4 Complete docs/API/workflow/evidence references for tickets, continuation, tools, RAG, trace, and offline eval CLI.
- [x] 6.5 Complete project overview, deep-dive explanation, and common Q&A in engineering notes.
- [x] 6.6 Run final Python tests, frontend build, OpenSpec validate, Docker Compose config, eval summary, and FastAPI smoke when Go API is available.
- [x] 6.7 Save Phase 6 evidence files and confirm boundaries: no LLM, no vector DB, no full MCP Server, no new ticket types, no Go repository edits.

## Phase 6.5: Optional LLM Summary Node
- [x] 6.5.1 Update OpenSpec for optional LLM summary refinement before implementation.
- [x] 6.5.2 Add LLM config, OpenAI-compatible HTTP client, and prompt template `finance_ticket_summary_v1`.
- [x] 6.5.3 Add optional LangGraph `llm_summarize` node after deterministic `summarize` and before `escalation_check`.
- [x] 6.5.4 Record `llm_skipped`, `llm_call`, and `llm_fallback` trace events without secrets or full prompt text.
- [x] 6.5.5 Preserve deterministic fallback when LLM is disabled, missing API key, failed, invalid JSON, or missing required fields.
- [x] 6.5.6 Prevent LLM output from downgrading `needs_human=true` or changing tool calls, evidence, ticket type, or metadata.
- [x] 6.5.7 Add fake-client tests for skipped, success, invalid JSON, exception fallback, escalation preservation, and eval stability.
- [x] 6.5.8 Update README, docs, evidence index, and engineering notes for optional LLM behavior and boundaries.
- [x] 6.5.9 Run Python tests, frontend build, OpenSpec validate, Docker Compose config, and offline eval evidence.
- [x] 6.5.10 Align optional LLM docs with DeepSeek Chat Completions: provider `deepseek`, model `deepseek-v4-flash`, base URL `https://api.deepseek.com`, JSON Output, and 20-second timeout example.
- [x] 6.5.11 Add a clear JSON output example to prompt `finance_ticket_summary_v1` while preserving evidence/tool-output-only constraints and human-escalation safeguards.
- [x] 6.5.12 Add optional `LLM_MAX_TOKENS` config with safe default and include `max_tokens` in Chat Completions payload.
- [x] 6.5.13 Add tests for prompt JSON example, `response_format=json_object`, and `LLM_MAX_TOKENS` payload/config behavior.
- [x] 6.5.14 Run DeepSeek-ready validation evidence and optional redacted real-model smoke when a local API key is configured.
