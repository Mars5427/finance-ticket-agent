# API 文档

## 运行入口

### 裸机

- Frontend: `http://127.0.0.1:5173`
- FastAPI docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/healthz`

### Docker

- Frontend: `http://127.0.0.1:5173`
- FastAPI docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/healthz`

Docker 模式下，浏览器访问的 `/api` 请求由 frontend 容器内的 Nginx 代理到 `agent-api` 容器。

## 环境变量

Agent API 使用以下环境变量：

- `GO_ACCOUNT_API_BASE_URL`
- `LLM_ENABLED`
- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_BASE_URL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_TOKENS`

Docker 默认值：

```text
GO_ACCOUNT_API_BASE_URL=http://host.docker.internal:8080
LLM_ENABLED=false
LLM_PROVIDER=disabled
LLM_TIMEOUT_SECONDS=10
LLM_MAX_TOKENS=800
```

Go 账户交易系统需要单独启动，或由外部环境提供可访问地址。

## HTTP API

### `GET /healthz`

健康检查。

响应：

```json
{"status": "ok"}
```

### `POST /api/tickets`

创建工单并立即执行 workflow。

请求示例：

```json
{
  "title": "余额异常解释",
  "description": "账户余额比我预期少 500，帮我解释一下。",
  "metadata": {
    "account_id": "demo-account",
    "observed_balance": 1500
  }
}
```

响应示例：

```json
{
  "id": "ticket_xxx",
  "title": "余额异常解释",
  "description": "账户余额比我预期少 500，帮我解释一下。",
  "type": "balance_anomaly",
  "status": "completed",
  "metadata": {
    "account_id": "demo-account",
    "observed_balance": 1500
  },
  "dialogue_context": [],
  "result": {
    "summary": "...",
    "evidence": [],
    "tool_calls": [],
    "needs_human": false,
    "escalation_reason": null,
    "follow_up_question": null
  },
  "trace": [],
  "created_at": "2026-08-04T00:00:00Z",
  "updated_at": "2026-08-04T00:00:00Z"
}
```

### `GET /api/tickets`

返回当前内存中的工单列表。

### `GET /api/tickets/{ticket_id}`

返回单个工单详情，包括：

- `status`
- `metadata`
- `dialogue_context`
- `result.summary`
- `result.evidence`
- `result.tool_calls`
- `result.needs_human`
- `result.escalation_reason`
- `trace`

### `GET /api/tickets/{ticket_id}/trace`

返回该工单的 trace 时间线。

典型 trace payload：

```json
{
  "tool_name": "list_account_transactions",
  "input": {"account_id": "demo-account", "limit": 50},
  "output": {"entries": []},
  "status": "succeeded",
  "elapsed_ms": 12,
  "error": null
}
```

RAG trace payload：

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

### `POST /api/tickets/{ticket_id}/continue`

对 `needs_more_info` 工单做同工单补参继续执行。

请求示例：

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

- 保留原 `ticket_id`
- 合并 `metadata`
- 追加当前工单内 `dialogue_context`
- 保留原 trace 并追加 continuation 事件
- 重新执行 workflow

错误：

- 404：工单不存在
- 409：工单不是 `needs_more_info`
- 422：`metadata_patch` 不是 JSON object

### `GET /api/tools`

返回当前已注册工具的元数据。

示例：

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

## 内部工具接口

这些接口不直接暴露给浏览器，而是由 Tool Registry 调用外部 Go 服务。

### `get_account`

- Go API: `GET /v1/accounts/{id}`

### `list_account_transactions`

- Go API: `GET /v1/accounts/{id}/transactions`

### `get_transaction_detail`

- Go API: `GET /v1/transfers/{id}`

### `check_account_reconciliation`

- Go API: `GET /v1/accounts/{id}/reconciliation`

对账最终判断会同时比较：

- `current_balance`
- `latest_ledger_balance_after`
- 用户传入的 `metadata.expected_balance`

## LLM 说明

当前没有新增强制 HTTP API。LLM 只在 LangGraph 内部作为可选 `llm_summarize` 节点使用。

默认关闭。无 Key 时：

- workflow 正常执行
- trace 记录 `llm_skipped`
- 离线评估保持稳定

如启用 DeepSeek 兼容配置：

```powershell
$env:LLM_ENABLED="true"
$env:LLM_PROVIDER="deepseek"
$env:LLM_API_KEY="<redacted>"
$env:LLM_MODEL="deepseek-v4-flash"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_TIMEOUT_SECONDS="20"
$env:LLM_MAX_TOKENS="800"
```

## 离线评估 CLI

当前没有强制 `GET /api/eval/summary` 之类的 HTTP 接口。

评估入口：

```powershell
cd D:\finance-ticket-agent\agent-api
python scripts\run_eval.py
```

保存输出：

```powershell
python scripts\run_eval.py --output ..\docs\evidence\phase6-eval-summary.json
```

## 当前边界

- Agent 不直连数据库
- Compose 不负责编排 Go 服务
- 当前无持久化数据库
- 当前无 LLM metadata extraction 节点
- RAG 不是向量数据库
- 工具层不是完整 MCP Server
