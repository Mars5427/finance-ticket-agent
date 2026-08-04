# API 文档

当前为 Phase 6.5 API 文档。FastAPI HTTP 接口保持工单创建、查询、trace、工具元数据和同工单 continue；Phase 5 新增的是离线评估 CLI，Phase 6.5 没有新增强制 eval HTTP API。FastAPI 服务使用内存存储，重启后工单会清空。业务账户、流水、交易详情和对账核验数据只通过 Go 账户交易系统 HTTP API 获取，Agent API 不直连 PostgreSQL。RAG 使用本地 Markdown 知识库检索，不使用向量数据库；Phase 6.5 的 LLM summary 为可选能力，默认关闭。Phase 4.5 起只支持缺参工单的同 ticket_id 补参继续执行，不做完整多轮聊天、长期记忆或跨工单记忆。

## Agent API

### 创建工单

`POST /api/tickets`

用途：创建财务工单并触发当前 LangGraph workflow。Phase 4 已接入真实 Markdown RAG，Phase 4.5 已支持缺参工单的同工单 continue。

请求：

```json
{
  "title": "余额和预期不一致",
  "description": "账户余额比我预期少 500 元",
  "metadata": {
    "account_id": "uuid",
    "observed_balance": 1500
  }
}
```

响应：

```json
{
  "id": "ticket_001",
  "status": "completed",
  "type": "balance_anomaly",
  "result": {
    "summary": "...",
    "evidence": [],
    "tool_calls": [
      {
        "name": "get_account",
        "input": {"account_id": "uuid"},
        "output": {"id": "uuid", "balance": 1000},
        "status": "succeeded",
        "elapsed_ms": 12,
        "error": null
      }
    ],
    "needs_human": false,
    "escalation_reason": null,
    "follow_up_question": null
  },
  "trace": []
}
```

### 查询工单列表

`GET /api/tickets`

用途：查询内存中已创建的工单列表。

### 查询工单

`GET /api/tickets/{ticket_id}`

用途：查询工单状态、结构化输出、工具调用结果和人工升级判断。

### 查询 Trace

`GET /api/tickets/{ticket_id}/trace`

用途：查询 LangGraph 节点 trace，包括初始化上下文、分类、缺参、任务拆解、RAG 检索、工具调用、结构化输出、人工升级判断和 finalize。

工具调用 trace payload 包含：

```json
{
  "tool_name": "list_account_transactions",
  "input": {"account_id": "uuid", "limit": 50},
  "output": {"entries": []},
  "status": "succeeded",
  "elapsed_ms": 10,
  "error": null
}
```

RAG trace payload 包含：

```json
{
  "query": "出差餐补需要哪些材料 报销 发票 餐补 审批",
  "matched_sources": ["reimbursement-policy.md", "approval-rules.md"],
  "snippets": ["员工出差期间可按出差天数申请餐补..."],
  "scores": [0.82],
  "elapsed_ms": 1,
  "no_evidence_reason": null
}
```

无强相关依据时，`no_evidence_reason` 会说明知识库未检索到足够依据，workflow 不会编造制度结论。

### 继续处理缺参工单

`POST /api/tickets/{ticket_id}/continue`

用途：仅用于 Phase 4.5 的同工单缺参补参继续执行。它不是通用聊天接口，不做长期记忆或跨工单记忆。

请求：

```json
{
  "message": "账户是 demo-account，我看到的余额是 1500",
  "metadata_patch": {
    "account_id": "demo-account",
    "observed_balance": 1500
  }
}
```

行为：

- `ticket_id` 不变。
- 合并旧 `metadata` 与 `metadata_patch`。
- 保留旧 `title` 和 `description`。
- 追加 `message` 到当前工单内 `dialogue_context`。
- 保留旧 trace，并追加 `continue_ticket`、`metadata_patch_applied`、`dialogue_context_updated`。
- 重新运行 LangGraph workflow，更新 `status`、`result`、`evidence`、`tool_calls` 和 `updated_at`。

限制：

- 只支持 `needs_more_info` 工单。
- `dialogue_context` 只保存当前工单内的原始输入和补参历史。
- 不支持通用聊天、长期记忆或跨工单记忆。

错误：

- 未找到 ticket：404。
- 非 `needs_more_info` 工单：409。
- `metadata_patch` 不是 JSON object：422。

### 查询工具注册信息

`GET /api/tools`

用途：查看当前 Agent API 注册的 MCP 风格工具元数据。该接口用于开发验收和演示，不代表已经实现完整 MCP Server。

响应：

```json
[
  {
    "name": "get_account",
    "description": "Fetch account summary data from the Go account transaction service.",
    "input_schema": {"type": "object"},
    "output_schema": {"type": "object"}
  }
]
```

### 健康检查

`GET /healthz`

响应：

```json
{"status":"ok"}
```

## 内部 Tool Calling API

这些工具由 Agent 内部调用，不直接暴露给终端用户。Phase 2 已实现 Tool Registry 和 Go API client，Phase 3 由 LangGraph `execute_tools` 节点调用；当前仍未实现完整 MCP Server。

### get_account

Go API：`GET /v1/accounts/{id}`

输入：

```json
{
  "account_id": "uuid"
}
```

输出：

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "currency": "USD",
  "balance": 1000,
  "created_at": "2026-07-22T00:00:00Z"
}
```

### list_account_transactions

Go API：`GET /v1/accounts/{id}/transactions?limit=50`

输入：

```json
{
  "account_id": "uuid",
  "limit": 50
}
```

输出：

```json
{
  "entries": [
    {
      "id": 1,
      "transfer_id": "uuid",
      "account_id": "uuid",
      "direction": "debit",
      "amount": 500,
      "balance_after": 1000,
      "created_at": "2026-08-04T00:00:00Z"
    }
  ]
}
```

### get_transaction_detail

Go API：`GET /v1/transfers/{id}`

输入：

```json
{
  "transfer_id": "uuid"
}
```

输出：

```json
{
  "id": "uuid",
  "from_account_id": "uuid",
  "to_account_id": "uuid",
  "amount": 500,
  "currency": "USD",
  "status": "succeeded",
  "created_at": "2026-08-04T00:00:00Z",
  "completed_at": "2026-08-04T00:00:00Z"
}
```

### check_account_reconciliation

Go API：`GET /v1/accounts/{id}/reconciliation`

输入：

```json
{
  "account_id": "uuid"
}
```

对账工单最终判断还会比较用户传入的 `metadata.expected_balance`：

- `current_balance == latest_ledger_balance_after` 且 `current_balance == expected_balance`：完成。
- `current_balance == latest_ledger_balance_after` 但 `current_balance != expected_balance`：升级人工，说明内部一致但外部预期不一致。
- `expected_balance` 无法转换为整数：升级人工，说明字段格式不可用。
- Go `matched=false`：升级人工，说明内部账户与流水不一致。

输出：

```json
{
  "account_id": "uuid",
  "current_balance": 1500,
  "latest_ledger_balance_after": 1500,
  "matched": true,
  "issues": []
}
```

## 错误映射

工具层会把 Go API 错误映射为结构化失败结果：

```json
{
  "name": "get_account",
  "input": {"account_id": "missing"},
  "output": {
    "code": "NOT_FOUND",
    "status_code": 404,
    "payload": {"error": {"code": "NOT_FOUND"}}
  },
  "status": "failed",
  "elapsed_ms": 8,
  "error": "resource was not found"
}
```

如果工具失败，workflow 会保留 trace，并根据任务风险触发人工升级。

## Evidence 结构

Phase 4 的 `result.evidence` 来自真实 Markdown RAG：

```json
{
  "source": "reimbursement-policy.md",
  "heading": "差旅餐补",
  "snippet": "员工出差期间可按出差天数申请餐补。报销时需要提供出差申请单、行程记录和必要票据。",
  "score": 0.82,
  "chunk_id": "reimbursement-policy.md#2"
}
```

## LLM 配置与 trace

Phase 6.5 没有新增强制 HTTP API，只在 LangGraph 内部新增可选 `llm_summarize` 节点。默认不开启，未配置 Key 时仍可运行全部本地测试、前端构建和离线评估。

环境变量：

```powershell
$env:LLM_ENABLED="true"
$env:LLM_PROVIDER="deepseek" # deepseek / openai / disabled
$env:LLM_API_KEY="<redacted>"
$env:LLM_MODEL="deepseek-v4-flash"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_TIMEOUT_SECONDS="20"
$env:LLM_MAX_TOKENS="800"
```

Trace 事件：

```json
{
  "step": "llm_summarize",
  "event_type": "llm_skipped",
  "payload": {
    "provider": "disabled",
    "model": "",
    "prompt_version": "finance_ticket_summary_v1",
    "reason": "LLM_ENABLED is not true."
  }
}
```

```json
{
  "step": "llm_summarize",
  "event_type": "llm_call",
  "payload": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "prompt_version": "finance_ticket_summary_v1",
    "elapsed_ms": 320,
    "input_summary_length": 120,
    "output_summary_length": 160,
    "confidence": "medium"
  }
}
```

```json
{
  "step": "llm_summarize",
  "event_type": "llm_fallback",
  "payload": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "prompt_version": "finance_ticket_summary_v1",
    "error": "LLM output missing required field: summary",
    "fallback_reason": "Keep deterministic summary because LLM request or output validation failed."
  }
}
```

API Key、敏感 header 和完整 prompt 不会写入 trace。LLM 输出只能更新 summary 和更保守的人工升级建议，不能改写 evidence、tool_calls、ticket_type、metadata，也不能把 deterministic `needs_human=true` 改成 false。

## 离线评估 CLI

Phase 5 没有新增必选 HTTP API，评估通过命令行运行：

```powershell
cd D:\finance-ticket-agent\agent-api
python scripts\run_eval.py
```

可将结果保存为 JSON：

```powershell
python scripts\run_eval.py --output ..\docs\evidence\phase6-eval-summary.json
```

输出包含：

- `total_cases`
- `task_completion_rate`
- `status_match_rate`
- `average_tool_call_count`
- `human_escalation_ratio`
- `rag_evidence_coverage`
- `continuation_success_rate`
- `failure_type_distribution`

`failure_type_distribution` 当前包含 `no_evidence`、`tool_failure`、`missing_parameters`、`expected_balance_mismatch`、`internal_reconciliation_mismatch`、`invalid_expected_balance`、`unsupported_scope`、`status_mismatch`、`type_mismatch`。

评估使用固定 cases 和 FakeRegistry，不依赖真实 Go 服务，不直连数据库，并显式禁用 LLM。指标只用于工程验收和本地质量回归，不代表线上准确率或模型效果。
