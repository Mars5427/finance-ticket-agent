# finance-ticket-agent-mvp Specification

## ADDED Requirements

### Requirement: Focused project scope

The system SHALL implement only the defined financial ticket Agent scope for the MVP.

#### Scenario: Supported ticket classes
- **WHEN** a ticket is submitted
- **THEN** the system classifies it into reimbursement policy Q&A, balance anomaly explanation, reconciliation anomaly localization, or unsupported

#### Scenario: Unsupported business expansion
- **WHEN** a request asks for a business domain outside the three supported ticket types
- **THEN** the system marks it unsupported or escalated instead of inventing new capabilities

### Requirement: Agent workflow behavior

The system SHALL support classification, missing-parameter follow-up, task decomposition, tool selection, result summarization, and human escalation judgment.

#### Scenario: Missing required parameters
- **WHEN** a balance anomaly ticket lacks account id or observed balance
- **THEN** the system records a missing-parameter trace event and returns a follow-up question

#### Scenario: Completed task
- **WHEN** all required inputs and evidence are available
- **THEN** the system returns a structured result with ticket type, conclusion, evidence, tool calls, and escalation decision

#### Scenario: Human escalation
- **WHEN** evidence is missing, conflicting, or insufficient for a reliable answer
- **THEN** the system marks the ticket as escalated and records the reason

### Requirement: MCP-style Tool Registry

The system SHALL define every business tool with explicit metadata suitable for future MCP exposure.

#### Scenario: Tool metadata
- **WHEN** a tool is registered
- **THEN** it has `name`, `description`, `input_schema`, and `output_schema`

#### Scenario: No direct database access
- **WHEN** the Agent needs account or transaction data
- **THEN** it calls a registered tool that uses the Go HTTP API instead of directly querying PostgreSQL

### Requirement: Go account service tool boundary

The system SHALL reuse the Go account transaction service as the business data backend through Tool Calling APIs.

#### Scenario: Account lookup
- **WHEN** `get_account` is called with a valid account id
- **THEN** the tool calls the Go account API and returns normalized account data or a structured error

#### Scenario: Ledger lookup
- **WHEN** `list_account_transactions` is called with an account id and optional limit
- **THEN** the tool calls the Go ledger API and returns normalized ledger entries or a structured error

#### Scenario: Go HTTP boundary
- **WHEN** transaction-detail or reconciliation data is needed
- **THEN** the Agent calls the Go service over `GET /v1/transfers/{id}` or `GET /v1/accounts/{id}/reconciliation` through registered tools
- **AND** the Agent does not modify the Go repository or query the Go service database directly

### Requirement: Phase 2 MCP-style Tool Registry and Go API client

The system SHALL implement a MCP-style Tool Registry and call the Go account transaction service over HTTP only.

#### Scenario: Registry exposes tool contracts
- **WHEN** the Agent API starts
- **THEN** the registry contains `get_account`, `list_account_transactions`, `get_transaction_detail`, and `check_account_reconciliation`
- **AND** each tool has `name`, `description`, `input_schema`, `output_schema`, `handler`, and error mapping behavior

#### Scenario: Account tool call
- **WHEN** `get_account` is called with `account_id`
- **THEN** it calls `GET /v1/accounts/{id}` and returns normalized account JSON or a mapped tool error

#### Scenario: Ledger tool call
- **WHEN** `list_account_transactions` is called with `account_id` and optional `limit`
- **THEN** it calls `GET /v1/accounts/{id}/transactions` and returns normalized ledger entries or a mapped tool error

#### Scenario: Transfer detail tool call
- **WHEN** `get_transaction_detail` is called with `transfer_id`
- **THEN** it calls `GET /v1/transfers/{id}` and returns normalized transfer JSON or a mapped tool error

#### Scenario: Reconciliation tool call
- **WHEN** `check_account_reconciliation` is called with `account_id`
- **THEN** it calls `GET /v1/accounts/{id}/reconciliation` and returns normalized reconciliation JSON or a mapped tool error

#### Scenario: Expected balance comparison
- **WHEN** a reconciliation anomaly ticket has `metadata.expected_balance`
- **THEN** the workflow compares Go `current_balance`, Go `latest_ledger_balance_after`, and the user-provided `expected_balance`
- **AND** a mismatch between `current_balance` and `expected_balance` is escalated even when Go internal reconciliation returns `matched=true`

#### Scenario: Invalid expected balance
- **WHEN** `metadata.expected_balance` cannot be converted to an integer
- **THEN** the ticket is escalated with a structured explanation instead of crashing

#### Scenario: Tool trace
- **WHEN** any registered tool runs during ticket handling
- **THEN** trace records tool name, input, output, status, elapsed milliseconds, and error message if failed

#### Scenario: Phase boundary
- **WHEN** Phase 2 is complete
- **THEN** the system still does not use LangGraph, does not perform real RAG retrieval, and does not expose a full MCP Server

### Requirement: Phase 3 LangGraph Agent Workflow

The system SHALL replace the deterministic orchestration shell with a LangGraph state graph while preserving the public Agent API response shape.

#### Scenario: LangGraph node sequence
- **WHEN** a ticket is created
- **THEN** the workflow runs through explicit nodes for `initialize_context`, `classify`, `check_missing_fields`, `plan`, `execute_tools`, `summarize`, `escalation_check`, and `finalize`
- **AND** trace events expose those workflow steps

#### Scenario: Missing parameters stop execution
- **WHEN** a supported ticket lacks required fields
- **THEN** LangGraph returns `needs_more_info` with a follow-up question
- **AND** no Go business tool is called

#### Scenario: Tool execution through registry
- **WHEN** a balance or reconciliation ticket has all required fields
- **THEN** LangGraph invokes existing registered tools instead of directly connecting to PostgreSQL
- **AND** tool history is retained in the structured result and trace

#### Scenario: Escalation checks
- **WHEN** tools fail, evidence is insufficient, Go internal reconciliation mismatches, expected balance mismatches, or the ticket type is unsupported
- **THEN** LangGraph marks the ticket for human escalation with an explicit reason

#### Scenario: Phase 3 boundary
- **WHEN** Phase 3 is complete
- **THEN** the system still does not perform real RAG retrieval, does not expose a full MCP Server, and does not support business scenarios outside the three supported ticket types

### Requirement: RAG with evidence snippets

The system SHALL retrieve finance-rule evidence from the project knowledge base and return source snippets in answers.

#### Scenario: Markdown ingestion
- **WHEN** the Agent API starts or a RAG retrieval is executed
- **THEN** Markdown files under `knowledge/` are chunked by heading and paragraph
- **AND** each chunk has `source`, `heading`, `content`, and `chunk_id`

#### Scenario: Reimbursement answer
- **WHEN** a reimbursement policy ticket is answered
- **THEN** the workflow retrieves from reimbursement policy and approval rules
- **AND** the answer includes relevant snippets with source, heading, snippet, and score

#### Scenario: Reconciliation SOP evidence
- **WHEN** a reconciliation anomaly ticket is processed
- **THEN** the workflow retrieves from the reconciliation SOP and uses matching snippets to explain manual review suggestions

#### Scenario: Balance anomaly SOP evidence
- **WHEN** a balance anomaly ticket is processed
- **THEN** the workflow may retrieve exception-handling SOP snippets
- **AND** it does not fabricate evidence when no strong match exists

#### Scenario: Conflicting rules
- **WHEN** retrieved snippets conflict or do not support a conclusion
- **THEN** the system escalates the ticket or states the limitation rather than hallucinating a rule

#### Scenario: RAG trace
- **WHEN** evidence retrieval runs
- **THEN** trace records `query`, matched sources, snippets, scores, elapsed milliseconds, and `no_evidence_reason` when no result is strong enough

#### Scenario: Phase 4 boundaries
- **WHEN** Phase 4 is complete
- **THEN** the system uses real Markdown retrieval but still does not use a vector database, does not call an LLM, does not expose a full MCP Server, and does not support same-ticket continuation after missing-parameter follow-up

### Requirement: Phase 4.5 ticket continuation

The system SHALL support lightweight same-ticket continuation after missing-parameter follow-up without becoming a general chat system.

#### Scenario: Continue a missing-parameter ticket
- **WHEN** a ticket is in `needs_more_info`
- **AND** the user submits a continuation message with `metadata_patch`
- **THEN** the system reuses the same `ticket_id`
- **AND** merges old metadata with `metadata_patch`
- **AND** preserves the old title and description
- **AND** re-runs the LangGraph workflow for that same ticket

#### Scenario: Continuation trace and context
- **WHEN** a ticket is continued
- **THEN** the old trace is retained
- **AND** new trace events include `continue_ticket`, `metadata_patch_applied`, and `dialogue_context_updated`
- **AND** dialogue context contains the original user input and the continuation message

#### Scenario: Continuation output update
- **WHEN** continuation supplies the missing required fields
- **THEN** the ticket status, result, evidence, tool calls, and updated timestamp are updated from the new workflow result
- **AND** the previous missing-parameter trace remains visible

#### Scenario: Missing ticket
- **WHEN** continuation is requested for an unknown `ticket_id`
- **THEN** the API returns 404

#### Scenario: Invalid metadata patch
- **WHEN** `metadata_patch` is not a JSON object
- **THEN** the API rejects the request with validation error behavior

#### Scenario: Phase 4.5 boundaries
- **WHEN** Phase 4.5 is complete
- **THEN** the system supports only lightweight same-ticket missing-parameter continuation
- **AND** it does not provide general chat, long-term memory, cross-ticket memory, LLM calls, a full MCP Server, or evaluation metrics

### Requirement: Trace and workbench visibility

The system SHALL expose execution trace for each ticket and visualize it in the frontend workbench.

#### Scenario: Trace inspection
- **WHEN** a user opens a ticket detail view
- **THEN** they can see classification, missing-parameter checks, task plan, tool parameters, tool returns, RAG snippets, elapsed time, failures, final conclusion, and escalation decision

### Requirement: Phase 1 deterministic vertical loop

The system SHALL provide a no-LLM deterministic loop before integrating LangGraph or model calls.

#### Scenario: Deterministic ticket creation
- **WHEN** a user creates one of the three supported ticket types through the FastAPI API
- **THEN** the system stores the ticket, runs deterministic classification and planning, records trace events, and returns a structured ticket result

#### Scenario: Deterministic missing-parameter follow-up
- **WHEN** a supported ticket lacks fields required for its task type
- **THEN** the system stores the ticket as `needs_more_info` and records a follow-up question without calling model or business tools

#### Scenario: Frontend trace display
- **WHEN** the React workbench loads ticket data from the API
- **THEN** it displays the ticket list, selected ticket details, execution steps, current status, and final conclusion or escalation reason

### Requirement: Evaluation cases and metrics

The system SHALL maintain sample tickets and compute simple evaluation metrics after implementation.

#### Scenario: Fixed offline cases
- **WHEN** Phase 5 evaluation runs
- **THEN** it loads at least 10 fixed cases from `eval_cases/finance_tickets.json`
- **AND** the cases cover reimbursement policy, balance anomaly, reconciliation anomaly, missing-parameter follow-up, same-ticket continuation, no-evidence escalation, tool-failure escalation, expected-balance mismatch, and unsupported scope

#### Scenario: No external service dependency
- **WHEN** evaluation runs in the local project
- **THEN** it uses an injected fake tool registry or equivalent deterministic test double
- **AND** it does not require the real Go account transaction service
- **AND** it does not query PostgreSQL directly

#### Scenario: Metrics output
- **WHEN** evaluation completes
- **THEN** it outputs `total_cases`, `task_completion_rate`, `status_match_rate`, `average_tool_call_count`, `human_escalation_ratio`, `rag_evidence_coverage`, `continuation_success_rate`, and `failure_type_distribution`

#### Scenario: Failure type distribution
- **WHEN** a case misses expected type, status, evidence, tool calls, continuation behavior, or trace events
- **THEN** the runner classifies the failure into stable categories such as `no_evidence`, `tool_failure`, `missing_parameters`, `expected_balance_mismatch`, `internal_reconciliation_mismatch`, `invalid_expected_balance`, `unsupported_scope`, `status_mismatch`, and `type_mismatch`

#### Scenario: Evaluation boundaries
- **WHEN** Phase 5 is complete
- **THEN** metrics are documented as fixed-case engineering validation only
- **AND** the system still does not call an LLM, use a vector database, expose a full MCP Server, expand ticket types, or modify the Go repository

#### Scenario: Evaluation run
- **WHEN** evaluation cases are executed
- **THEN** the system reports task completion rate, average tool call count, human escalation ratio, and failure type distribution

### Requirement: Phase 6 final engineering handoff

The system SHALL provide final documentation and evidence that make the project ready for local demo, review, and future iteration.

#### Scenario: Feature-goal alignment
- **WHEN** Phase 6 is complete
- **THEN** README, design documentation, and engineering notes include a table mapping each feature goal to concrete implementation files and validation evidence

#### Scenario: Demo and operation documentation
- **WHEN** a reader opens the README or API docs
- **THEN** they can find the project positioning, stack, architecture, startup commands, API examples, frontend demo path, eval command, evidence file index, and explicit limitations

#### Scenario: Engineering notes
- **WHEN** a reader reviews the project
- **THEN** engineering notes provide concise overviews, deep-dive explanations, and answers to common follow-up questions about database boundaries, Tool Calling, MCP-style registry, LangGraph, RAG, continuation, evaluation metrics, Go service role, CRUD differences, and follow-up iterations

#### Scenario: Final evidence
- **WHEN** final validation runs
- **THEN** Phase 6 evidence files record Python unit tests, frontend build, OpenSpec strict validation, Docker Compose config, eval summary, and FastAPI smoke if the Go API is available

#### Scenario: Final boundaries
- **WHEN** Phase 6 is complete
- **THEN** the project still does not call an LLM, use a vector database, expose a full MCP Server, implement generic multi-turn chat or long-term memory, claim online accuracy, expand beyond three financial ticket types, or modify the Go account transaction repository

### Requirement: Optional LLM summary refinement

The system SHALL support an optional LLM summary node that refines deterministic structured conclusions without becoming a dependency for local execution.

#### Scenario: Default disabled behavior
- **WHEN** no LLM API key is configured or `LLM_ENABLED` is not true
- **THEN** the workflow keeps the deterministic summary
- **AND** trace records `llm_skipped` with a non-sensitive reason
- **AND** tests, frontend build, Docker config, and offline evaluation can run fully locally

#### Scenario: Successful LLM refinement
- **WHEN** LLM configuration is enabled and the OpenAI-compatible chat completions call returns valid JSON with `summary`, `needs_human`, `escalation_reason`, and `confidence`
- **THEN** the workflow may update the result summary with the refined text
- **AND** trace records `llm_call` with provider, model, prompt version, elapsed milliseconds, input summary length, and output summary length
- **AND** trace does not include API keys, sensitive headers, or the full prompt text

#### Scenario: DeepSeek JSON Output alignment
- **WHEN** a DeepSeek smoke is configured
- **THEN** docs and config examples use provider `deepseek`, model `deepseek-v4-flash`, base URL `https://api.deepseek.com`, and path `/chat/completions`
- **AND** the client payload includes `response_format={"type":"json_object"}` and a bounded `max_tokens`
- **AND** the prompt includes a concrete JSON output example with `summary`, `needs_human`, `escalation_reason`, and `confidence`

#### Scenario: Fallback on invalid model output
- **WHEN** the model request fails, returns invalid JSON, or omits required fields
- **THEN** the workflow keeps the deterministic summary and escalation decision
- **AND** trace records `llm_fallback` with provider, model, prompt version, error, and fallback reason

#### Scenario: Escalation boundary
- **WHEN** deterministic business logic has already set `needs_human=true`
- **THEN** LLM output MUST NOT change the ticket to non-escalated or remove the human-review boundary

#### Scenario: Fact source boundary
- **WHEN** the LLM summary node runs
- **THEN** it can use only ticket metadata, deterministic summary, RAG evidence snippets, and tool call outputs as input
- **AND** it MUST NOT alter tool calls, evidence, ticket type, metadata, classification, RAG retrieval, or Tool Registry behavior
- **AND** the project still does not implement a full MCP Server, vector database RAG, new ticket types, general chat, long-term memory, cross-ticket memory, or Go repository changes
