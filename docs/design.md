# 设计文档

## 目标

构建一个边界清晰、可审计、可本地运行的财务工单 Agent 项目。第一版只覆盖三类代表性任务：

- 报销规则问答
- 余额异常解释
- 对账异常定位

项目终态需要覆盖分类、缺参追问、任务拆解、工具选择、Tool Calling、RAG、结构化输出、状态保持、执行 trace、人工升级、前端可视化和简单评估。当前进度停在 Phase 6：已经完成最终验收与工程文档收束。实现侧已用 LangGraph 接管 Agent Workflow，复用 Phase 2 的 Tool Registry 与 Go API 对接，实现真实 Markdown RAG，支持缺参追问后的同工单补参继续执行，并提供固定 eval cases 的离线评估指标。

## 目标技术选型

- FastAPI：提供 Agent API，负责工单创建、同工单缺参补参、查询、trace 查询和工具元数据查看。
- LangGraph：Phase 3 已用于显式建模 Agent Workflow 状态机。
- React + TypeScript：构建工单工作台，展示列表、详情、执行步骤、工具调用、RAG evidence、trace 和处理结论。
- Go 账户交易系统：Phase 2 已作为业务数据后端接入，复用账户、流水、交易详情和对账核验能力。
- PostgreSQL / Redis：由 Go 服务持有，Agent 不直连。
- RAG：Phase 4 已检索报销制度、审批标准、异常处理 SOP；当前实现是本地 Markdown chunk + 关键词/BM25-like scoring，不是向量数据库 RAG。
- Docker / OpenSpec：提供本地编排检查和规格驱动验收。
- Evaluation：Phase 5 使用固定 JSON cases + FakeRegistry 离线运行，不依赖真实 Go 服务。

## 架构边界

```text
React + TypeScript 前端工单工作台
        ↓
Python FastAPI Agent API
        ↓
LangGraph workflow，Phase 4.5 当前实现
        ↓
Markdown RAG + MCP 风格 Tool Registry
        ↓
Go 账户交易系统 HTTP API
        ↓
PostgreSQL / Redis
```

Phase 4 已在 LangGraph workflow 中加入 `retrieve_evidence` 节点。Phase 4.5 在缺参工单上加入同 `ticket_id` 的补参继续执行。Phase 6.5 新增可选 `llm_summarize` 节点；分类规则、RAG 和工具调用仍是确定性的，LLM 默认关闭且只润色总结。

## 状态机

```text
received
  -> classified
  -> needs_more_info | planned
  -> rag_retrieval
  -> tool_call
  -> summarized
  -> completed | escalated | failed
```

Phase 4.5 当前实现是 LangGraph 状态图：

- `initialize_context`：构建 title、description、metadata、ticket_id、dialogue_context、tool_history 和 trace；继续工单时识别 `continuation_message`，追加当前工单内补参历史，并保留旧 trace。
- `classify`：基于关键词分类为三类受支持工单或 unsupported。
- `check_missing_fields`：检查必填 metadata 并生成追问；缺参时不会执行 RAG 或 Go 工具。
- `plan`：记录任务拆解步骤和候选工具。
- `retrieve_evidence`：检索 Markdown 知识库并记录 `rag_retrieval` trace。
- `execute_tools`：只通过 Tool Registry 调用 Go HTTP API。
- `summarize`：基于真实 evidence、tool_calls 和业务判断生成 summary。
- `escalation_check`：根据缺证据、工具失败、内部对账 mismatch、expected_balance mismatch、unsupported 判断人工升级。
- `finalize`：保持 `TicketResponse` 外部结构兼容。

使用 LangGraph 的价值：

- 状态节点显式，便于理解和排查每一步的输入输出。
- 工具调用、RAG evidence、上下文、trace 和结构化输出都在统一 state 中流转。
- 后续接 LLM、评估或更完整对话能力时，可以替换单个节点，不需要推翻 API 和前端。
- 相比长 if-else，更容易插入人工升级、失败恢复和审计 trace。

## 工具层

Phase 2 已实现 MCP 风格 Tool Registry，但没有实现完整 MCP Server。每个工具定义包含：

- `name`
- `description`
- `input_schema`
- `output_schema`
- `handler`
- error mapping

已接入工具：

- `get_account`：调用 `GET /v1/accounts/{id}`。
- `list_account_transactions`：调用 `GET /v1/accounts/{id}/transactions`。
- `get_transaction_detail`：调用 `GET /v1/transfers/{id}`。
- `check_account_reconciliation`：调用 `GET /v1/accounts/{id}/reconciliation`。

错误映射会把 HTTP 4xx/5xx、Go 服务不可用、超时、非 JSON 响应转换为结构化工具失败结果，并写入 trace。Agent API 不直接连接 Go 服务背后的 PostgreSQL。

## Phase 6.5 可选 LLM Summary Node

Phase 6.5 在 LangGraph 中新增 `llm_summarize` 节点，位置是 `summarize -> llm_summarize -> escalation_check`。它只负责把 deterministic summary 润色为更自然的结构化结论，不负责分类、工具选择、RAG 检索或业务数据访问。

配置项：
- `LLM_ENABLED`：默认 false。
- `LLM_PROVIDER`：`openai` / `deepseek` / `disabled`，默认 disabled。
- `LLM_API_KEY`：仅从环境变量读取，不能写入文档、trace 或 evidence。
- `LLM_MODEL`：模型名。
- `LLM_BASE_URL`：OpenAI-compatible Chat Completions base URL。
- `LLM_TIMEOUT_SECONDS`：请求超时时间。
- `LLM_MAX_TOKENS`：可选输出 token 上限，默认 800；DeepSeek smoke 建议 800。

DeepSeek smoke 推荐配置：

```powershell
$env:LLM_ENABLED="true"
$env:LLM_PROVIDER="deepseek"
$env:LLM_API_KEY="<redacted>"
$env:LLM_MODEL="deepseek-v4-flash"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_TIMEOUT_SECONDS="20"
$env:LLM_MAX_TOKENS="800"
```

Prompt 版本为 `finance_ticket_summary_v1`。输入包括工单类型、标题、描述、metadata、deterministic summary、RAG evidence snippets、tool_calls、needs_human 和 escalation_reason。Prompt 约束模型只能基于 evidence 和 tool outputs 作答，不得编造制度、余额、流水或交易，并要求输出 JSON：`summary`、`needs_human`、`escalation_reason`、`confidence`。

fallback 规则：
- disabled 或无 Key：记录 `llm_skipped`，保留 deterministic summary。
- HTTP 失败、异常、非法 JSON 或缺字段：记录 `llm_fallback`，保留 deterministic summary。
- 成功：记录 `llm_call`，只保存 provider、model、prompt_version、elapsed_ms 和 summary 长度，不保存 API Key、header 或完整 prompt。
- deterministic 规则已经 `needs_human=true` 时，LLM 不能改成 false，也不能改写 tool_calls、evidence、ticket_type 或 metadata。

离线评估 runner 显式传入 disabled LLM 配置，因此固定 cases 不依赖外网或模型 Key，指标也不代表 LLM 效果。

## RAG

Phase 4 已实现轻量 Markdown RAG。知识库文件：

- `knowledge/reimbursement-policy.md`
- `knowledge/approval-rules.md`
- `knowledge/reconciliation-sop.md`

Ingestion：

- 按 Markdown 标题和段落切 chunk。
- 每个 chunk 保存 `source`、`heading`、`content`、`chunk_id`。

Retrieval：

- 使用关键词/token overlap/BM25-like scoring。
- 每条结果返回 `source`、`heading`、`snippet`、`score`、`chunk_id`。
- 不使用向量数据库，不调用 LLM。

规则冲突、证据不足或查不到规则时，系统应触发人工升级或明确说明限制。RAG 的价值是让回答有依据、可追溯、可人工复核。

## 三类任务当前行为

### 报销规则问答

当前执行真实 Markdown RAG，检索 `reimbursement-policy.md` 和 `approval-rules.md`。回答必须返回 evidence snippets；查不到足够依据时会说明“知识库未检索到足够依据”并升级人工，不编造制度。

### 余额异常解释

必填字段：

- `account_id`
- `observed_balance`

执行路径：

```text
分类 -> 缺参检查 -> retrieve_evidence -> get_account -> list_account_transactions -> 必要时 get_transaction_detail -> 结构化总结 -> 失败时人工升级
```

余额异常会尝试检索异常处理 SOP。若无强相关依据，不强行生成 SOP 依据，只说明没有检索到强相关依据。

### 对账异常定位

必填字段：

- `account_id`
- `expected_balance`
- `time_range`

执行路径：

```text
分类 -> 缺参检查 -> retrieve_evidence -> list_account_transactions -> check_account_reconciliation -> 比较 expected_balance -> 结构化总结 -> mismatch 时人工升级
```

对账判断包含两层：

- 内部账实一致性：Go `check_account_reconciliation` 比较 `current_balance` 和 `latest_ledger_balance_after`。
- 外部预期一致性：workflow 比较用户传入的 `metadata.expected_balance` 和 Go `current_balance`。

如果 Go 内部 matched=true，但 `expected_balance` 与 `current_balance` 不一致，仍然升级人工，并说明内部账户与流水一致、外部对账单或用户预期不一致、差额是多少，以及建议复核外部对账单来源、时间范围或入账延迟。对账总结会附带 SOP 依据；如果知识库无依据，会明确说明。

## Trace

当前 Phase 4.5 trace 已记录：

- 工单分类
- 缺参检查
- 同工单 continue 事件
- metadata_patch 合并
- 当前工单 dialogue_context 追加
- 任务拆解
- RAG 查询、命中来源、片段、分数和 no_evidence_reason
- 工具调用
- 工具名称
- 工具输入
- 工具输出
- 工具状态
- 工具耗时
- 工具失败原因
- 结构化输出
- 人工升级判断

Phase 5 已基于固定 eval cases 输出离线评估指标。

## 数据边界

Agent 不直连 PostgreSQL。账户余额、流水、交易详情和对账核验数据只通过 Go HTTP API 获取。这样可以保留业务服务边界，避免模型绕过业务校验，也便于审计每一次工具调用。

FastAPI 当前仍使用内存存储工单状态、当前工单内 `dialogue_context` 和 trace，服务重启后工单会清空。账户、流水和交易数据的事实来源是 Go 账户交易系统。

Phase 4.5 已支持缺参追问后继续同一工单执行：仅当已有工单状态为 `needs_more_info` 时，用户可以通过 `POST /api/tickets/{ticket_id}/continue` 提交 `message` 和 `metadata_patch`。系统会合并 metadata、保留原 title/description/ticket_id、追加当前工单内 `dialogue_context`、保留旧 trace，并重新运行 LangGraph workflow。

这只是轻量多轮任务状态保持，不是完整多轮聊天系统，不做长期记忆，也不做跨工单记忆。

## 离线评估

Phase 5 已新增固定用例评估，评估入口：

```powershell
cd D:\finance-ticket-agent\agent-api
python scripts\run_eval.py
```

评估数据来自 `eval_cases/finance_tickets.json`，当前包含 12 条固定工单，覆盖：

- 报销规则问答正常完成
- 余额异常正常完成
- 对账异常正常完成
- 缺参 `needs_more_info`
- 同工单 continue 后完成
- RAG 无依据升级
- 工具失败升级
- expected_balance mismatch 升级
- unsupported 升级

评估 runner 使用 `EvaluationFakeRegistry`，不依赖真实 Go 服务，不直连 PostgreSQL，也不修改 Go 项目。这样评估可以在本地稳定重复运行，同时仍复用真实 LangGraph workflow、RAG 和 trace 逻辑。

输出指标：

- `total_cases`
- `task_completion_rate`
- `status_match_rate`
- `average_tool_call_count`
- `human_escalation_ratio`
- `rag_evidence_coverage`
- `continuation_success_rate`
- `failure_type_distribution`

失败类型分布包括 `no_evidence`、`tool_failure`、`missing_parameters`、`expected_balance_mismatch`、`internal_reconciliation_mismatch`、`invalid_expected_balance`、`unsupported_scope`、`status_mismatch`、`type_mismatch`。这些指标只用于固定 cases 的工程验收和本地质量回归，不代表线上准确率或生产业务质量。

## 功能目标与实现状态

| 功能目标 | 最终实现状态 | 关键文件 |
| --- | --- | --- |
| 三类财务工单 Agent Workflow：报销规则问答、余额异常解释、对账异常定位；分类、缺参追问、任务拆解、工具选择、结果汇总、人工升级。 | 已满足。LangGraph 节点显式承载分类、缺参、plan、RAG、工具执行、总结、升级；只覆盖三类受支持任务。 | `agent-api/app/workflow.py`、`docs/agent-workflow.md` |
| FastAPI + LangGraph Agent 服务：工单状态、dialogue_context、metadata patch、tool_history、trace、结构化输出、可 MCP 化 Tool Registry。 | 已满足。`TicketResponse` 包含状态、metadata、dialogue_context、result、trace；continue 接口合并 metadata_patch；Tool Registry 提供工具契约。 | `agent-api/app/main.py`、`agent-api/app/models.py`、`agent-api/app/tools/registry.py` |
| 复用 Go 账户交易服务：get_account、list_account_transactions、get_transaction_detail、check_account_reconciliation；Agent 不直连 PostgreSQL。 | 已满足。工具层通过 Go HTTP API 调用账户、流水、交易详情、对账核验；Agent 侧没有数据库直连依赖。 | `agent-api/app/tools/go_client.py`、`agent-api/app/tools/registry.py` |
| 财务规则知识库 + Markdown RAG：报销制度、审批标准、异常处理 SOP；返回 source/heading/snippet/score/chunk_id；无依据不编造。 | 已满足。知识库 Markdown 分块和轻量检索已实现；summary 和 trace 返回 evidence；无依据时说明限制或升级人工。 | `agent-api/app/rag/`、`knowledge/` |
| Trace + React 工作台 + Eval：工单创建/列表/详情、RAG evidence、工具参数/返回/耗时/错误、补参 trace、12 条固定 eval cases、任务完成率、平均工具调用次数、人工升级比例、失败类型分布。 | 已满足。前端展示 trace/tool/evidence/结论；评估 runner 输出固定 cases 指标。 | `frontend/src/main.tsx`、`agent-api/app/evaluation/runner.py`、`eval_cases/finance_tickets.json` |

## Phase 6 验证

Phase 6 验证证据保存在 `docs/evidence/`：

- `phase6-python-unittest.txt`
- `phase6-frontend-build.txt`
- `phase6-openspec-validate.txt`
- `phase6-docker-compose-config.txt`
- `phase6-eval-summary.json`
- `phase6-fastapi-smoke.txt`

## 下一步计划

Phase 6 完成后暂停。后续迭代建议聚焦完整 MCP Server、持久化工单状态、向量检索和更系统的评估能力，而不是继续无边界扩展工单类型。
