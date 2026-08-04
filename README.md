# 面向财务场景的智能工单处理 Agent

这是一个面向财务工单处理的 AI 全栈 Agent 示例项目，聚焦可审计的 Agent Workflow、受控工具调用、RAG 依据检索、前端工作台和可重复的工程验收。

## 项目定位

这是一个面向财务工单的 AI 全栈项目，不是泛聊天机器人，也不是支付、清结算或生产风控系统。第一版只覆盖三类代表性任务：

1. 报销规则问答
2. 余额异常解释
3. 对账异常定位

项目目标是展示 Agent Workflow、Tool Calling、RAG、前后端工作台、trace 和工程化验收，而不是扩张成企业全业务平台。

## 技术栈

Python, FastAPI, LangGraph, React, TypeScript, Go, PostgreSQL, Redis, RAG, Tool Calling, Docker, OpenSpec

## 目标架构

```text
React + TypeScript 前端工单工作台
        ↓
Python FastAPI Agent API
        ↓
LangGraph Agent Workflow，Phase 3 已接入
        ↓
MCP 风格 Tool Registry，Phase 2 已实现可 MCP 化元数据层
        ↓
Go 账户交易系统 HTTP API
        ↓
PostgreSQL / Redis，由 Go 服务持有
```

## 为什么 Agent 不直连 PostgreSQL

Agent 只能通过 Tool Calling 访问 Go 账户交易服务，不能直接连接 Go 服务背后的 PostgreSQL。

原因：

- Go 账户交易服务已经封装账户、流水、交易详情、对账核验、事务和限流边界。
- Tool Calling 能把 Agent 能做的事情限制在可审计的工具能力内。
- 工具层可以记录参数、返回值、耗时和失败原因，便于 trace 和问题复盘。
- 直接暴露数据库会绕过业务校验，也会让模型接触过宽的数据面。

## 当前阶段

当前已完成 Phase 6：最终验收与工程文档收束。

当前完成度判断：

- Phase 0：已完成规格与骨架。
- Phase 1：已完成无 LLM 的 deterministic workflow 端到端闭环。
- Phase 2：已完成工具注册层、Go HTTP API client、4 个业务工具、工具调用 trace、前端工具调用结果展示。
- Phase 3：已完成 LangGraph 状态图，包含初始化上下文、分类、缺参检查、任务拆解、工具执行、总结、人工升级判断和 finalize。
- Phase 4：已完成真实 Markdown RAG，能检索报销制度、审批标准和对账异常 SOP，并在回答与 trace 中返回来源、片段和分数。
- Phase 4.5：已支持 needs_more_info 工单通过同一个 ticket_id 补充 metadata 后继续执行，保留旧 trace 和当前工单内 dialogue_context。
- Phase 5：已完成固定 eval cases 和离线评估脚本，输出任务完成率、状态匹配率、平均工具调用次数、人工升级比例、RAG 依据覆盖率、continue 成功率和失败类型分布。
- Phase 6：已完成功能目标对照、文档收束、工程说明和最终验证证据。

已完成：

- FastAPI 工单 API：创建工单、查询工单、查询 trace。
- LangGraph workflow：三类工单的分类、缺参追问、任务拆解、工具执行、结构化输出和人工升级边界。
- MCP 风格 Tool Registry：每个工具包含 `name`、`description`、`input_schema`、`output_schema`、`handler` 和错误映射。
- Go API 工具：`get_account`、`list_account_transactions`、`get_transaction_detail`、`check_account_reconciliation`。
- 余额异常解释会调用账户查询、流水查询，并在有 transfer id 时调用交易详情。
- 对账异常定位会调用流水查询和对账核验。
- 对账判断包含两层：Go 内部 `current_balance` 与 `latest_ledger_balance_after` 的账实一致性，以及用户 `metadata.expected_balance` 与 Go 当前余额的外部预期差异。
- Markdown RAG：按标题/段落切分 `knowledge/` 文档，使用轻量关键词/BM25-like scoring 检索，返回 `source`、`heading`、`snippet`、`score`、`chunk_id`。
- 报销规则问答必须使用报销制度和审批标准依据；对账异常会检索 SOP 辅助人工复核建议；余额异常可检索 SOP，低相关时不强行编造依据。
- Ticket continue：`POST /api/tickets/{ticket_id}/continue` 可对 `needs_more_info` 工单合并 `metadata_patch`、追加补参 message、保留旧 trace，并重新运行同一工单。
- Trace 记录工具名称、输入、输出、状态、耗时和失败原因。
- 离线评估：`eval_cases/finance_tickets.json` 已包含 12 条固定评测工单；`agent-api/scripts/run_eval.py` 使用 FakeRegistry 运行，不依赖真实 Go 服务。
- React + TypeScript 工单工作台展示工单创建、列表、详情、执行步骤、工具调用结果、依据片段、结论和人工升级状态。

## 功能目标对照

| 功能目标 | 当前实现对齐 | 关键文件 | 验证证据 |
| --- | --- | --- | --- |
| 1. 设计面向财务工单的 Agent Workflow，覆盖报销规则问答、余额异常解释、对账异常定位，实现分类、缺参追问、任务拆解、工具选择、结果汇总与人工升级判断。 | 已满足。LangGraph workflow 覆盖三类工单；`check_missing_fields` 处理缺参；`plan` 记录任务拆解和候选工具；`summarize` 与 `escalation_check` 输出结论和人工升级。 | `agent-api/app/workflow.py`、`docs/agent-workflow.md` | `docs/evidence/phase6-python-unittest.txt`、`docs/evidence/phase6-fastapi-smoke.txt` |
| 2. 基于 Python/FastAPI + LangGraph 构建 Agent 服务，维护工单状态、对话上下文、工具调用历史与结构化输出；设计可 MCP 化工具注册层。 | 已满足。FastAPI 暴露工单 API；LangGraph state 维护 `dialogue_context`、`tool_history`、trace 和 `TicketResponse`；Tool Registry 暴露 name/description/schema/handler/error mapping。 | `agent-api/app/main.py`、`agent-api/app/models.py`、`agent-api/app/tools/registry.py` | `phase6-python-unittest.txt`、`phase6-openspec-validate.txt` |
| 3. 复用并升级 Go 账户交易服务作为业务数据后端，封装账户查询、流水检索、交易详情、对账核验等 Tool Calling API。 | 已满足。Agent 只通过 Go HTTP API 工具访问账户、流水、交易详情和对账核验，不直连 PostgreSQL。 | `agent-api/app/tools/go_client.py`、`agent-api/app/tools/registry.py`、`docs/api.md` | `phase6-fastapi-smoke.txt`、历史 `phase2-go-api-connectivity.txt` |
| 4. 构建财务规则知识库，支持报销制度、审批标准、异常处理 SOP 的 RAG 检索，并在回答中返回依据片段，降低模型凭空回答风险。 | 已满足。Markdown RAG 检索 `knowledge/` 文档，返回 source、heading、snippet、score、chunk_id；无依据时不编造，必要时升级人工。 | `agent-api/app/rag/`、`knowledge/`、`docs/agent-workflow.md` | `phase6-python-unittest.txt`、`phase6-eval-summary.json` |
| 5. 实现 Agent 执行 trace 与前端工单工作台，展示工单列表、执行步骤、工具参数/返回结果、耗时、失败原因与处理结论，并沉淀测试工单样例用于评估任务完成率、平均工具调用次数和人工升级比例。 | 已满足。React 工作台展示工单创建、列表、详情、trace、tool_calls、evidence、结论和补参；离线 eval 输出 completion/tool/escalation/failure 指标。 | `frontend/src/main.tsx`、`agent-api/app/evaluation/runner.py`、`eval_cases/finance_tickets.json` | `phase6-frontend-build.txt`、`phase6-eval-summary.json` |

尚未实现：

- 完整 MCP Server；当前只是可 MCP 化工具注册层。
- 完整多轮聊天、长期记忆、跨工单记忆。
- 真实线上准确率、生产质量指标或模型效果指标；当前评估只来自固定离线 cases。

## 本地启动

先启动 Go 账户交易系统；如未启动，请在另一个终端进入原 Go 项目运行其 Docker Compose，不要在本项目直接修改 Go 源码：

```powershell
cd D:\Career_Research\go-account-transaction
docker compose up -d
```

启动 FastAPI：

```powershell
cd D:\finance-ticket-agent\agent-api
$env:GO_ACCOUNT_API_BASE_URL="http://127.0.0.1:8080"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
cd D:\finance-ticket-agent\frontend
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

FastAPI 文档：

```text
http://127.0.0.1:8000/docs
```

前端演示路径：

```text
http://127.0.0.1:5173
```

建议演示顺序：

1. 创建报销规则工单，展示 RAG evidence。
2. 创建余额异常工单，展示 Go 工具调用和 trace。
3. 创建 expected_balance mismatch 的对账工单，展示人工升级原因。
4. 创建缺参余额工单，再在同一个 ticket 上 continue 补参，展示旧 trace 保留和新工具调用。

## API 示例

创建工单：

```powershell
$body = @{
  title = "余额异常解释"
  description = "账户余额比我预期少 500，帮我解释一下。"
  metadata = @{ account_id = "<account-id>"; observed_balance = 1500 }
} | ConvertTo-Json -Depth 10
$body | curl.exe -s -X POST http://127.0.0.1:8000/api/tickets -H "Content-Type: application/json" --data-binary '@-'
```

继续缺参工单：

```powershell
$body = @{
  message = "账户是 demo-account，我看到的余额是 1500"
  metadata_patch = @{ account_id = "demo-account"; observed_balance = 1500 }
} | ConvertTo-Json -Depth 10
$body | curl.exe -s -X POST http://127.0.0.1:8000/api/tickets/<ticket-id>/continue -H "Content-Type: application/json" --data-binary '@-'
```

查询工单、trace 和工具：

```powershell
curl.exe -s http://127.0.0.1:8000/api/tickets
curl.exe -s http://127.0.0.1:8000/api/tickets/<ticket-id>
curl.exe -s http://127.0.0.1:8000/api/tickets/<ticket-id>/trace
curl.exe -s http://127.0.0.1:8000/api/tools
```

## 离线评估

Phase 5/6.5 的评估不依赖真实 Go 服务，显式禁用 LLM，也不使用向量数据库。它读取固定评测工单，使用 FakeRegistry 走同一套 LangGraph workflow。

运行：

```powershell
cd D:\finance-ticket-agent\agent-api
python scripts\run_eval.py
```

保存为证据：

```powershell
cd D:\finance-ticket-agent\agent-api
python scripts\run_eval.py --output ..\docs\evidence\phase6-eval-summary.json
```

当前指标字段：

- `total_cases`
- `task_completion_rate`
- `status_match_rate`
- `average_tool_call_count`
- `human_escalation_ratio`
- `rag_evidence_coverage`
- `continuation_success_rate`
- `failure_type_distribution`

`failure_type_distribution` 当前细分为 `no_evidence`、`tool_failure`、`missing_parameters`、`expected_balance_mismatch`、`internal_reconciliation_mismatch`、`invalid_expected_balance`、`unsupported_scope`、`status_mismatch`、`type_mismatch`。

这些指标只代表固定 eval cases 的工程验收结果，不代表真实线上准确率，也不能写成夸张效果数字。

## Phase 6.5：可选 LLM Summary Node

Phase 6.5 新增的是可选的 LLM 总结润色节点，不改变三类工单范围，不替代 Tool Calling 和 RAG，也不是完整聊天机器人。workflow 仍然先由规则生成 deterministic summary，再在 `summarize` 之后、`escalation_check` 之前尝试执行 `llm_summarize`。

默认不配置 Key 时，系统完全本地运行：

```powershell
# 默认不需要设置任何 LLM 变量
# 如需启用兼容 Chat Completions 的模型，再显式设置：
$env:LLM_ENABLED="true"
$env:LLM_PROVIDER="deepseek" # deepseek / openai / disabled
$env:LLM_API_KEY="<redacted>"
$env:LLM_MODEL="deepseek-v4-flash"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_TIMEOUT_SECONDS="20"
$env:LLM_MAX_TOKENS="800"
```

Prompt 版本：`finance_ticket_summary_v1`。输入只包含 ticket_type、title、description、metadata、deterministic summary、RAG evidence snippets、tool_calls、needs_human 和 escalation_reason。Prompt 明确要求只能基于 evidence 和 tool outputs 作答，不得编造制度、余额、流水或交易；输出必须是 JSON：

```json
{
  "summary": "...",
  "needs_human": true,
  "escalation_reason": "...",
  "confidence": "low|medium|high"
}
```

fallback 行为：
- 未启用或无 API Key：保留 deterministic summary，trace 记录 `llm_skipped`。
- 模型请求失败、返回非法 JSON 或缺字段：保留 deterministic summary，trace 记录 `llm_fallback`。
- 模型成功：更新 summary，trace 记录 `llm_call`，但不记录 API Key、敏感 header 或完整 prompt。
- 如果规则已经判断 `needs_human=true`，LLM 不能把它改成 false，也不能改写 tool_calls、evidence、ticket_type 或 metadata。

离线 eval 显式使用 disabled LLM 配置，保证 12 条固定 cases 稳定可重复，不依赖外网或模型 Key。

真实 DeepSeek smoke 已通过，证据见 `docs/evidence/phase65-deepseek-real-smoke.txt`；该 smoke 只验证可选 LLM summary 节点能触发 `llm_call`，不代表线上生产验证或模型效果承诺。

## OpenSpec

当前 change：

```text
openspec/changes/bootstrap-finance-ticket-agent-mvp
```

验证命令：

```powershell
cd D:\finance-ticket-agent
openspec validate --all --strict
```

## 验收证据

证据文件保存在 `docs/evidence/`：

- `phase1-python-unittest.txt`
- `phase1-fastapi-smoke.txt`
- `phase1-frontend-build.txt`
- `phase1-openspec-validate.txt`
- `phase1-docker-compose-config.txt`
- `phase2-python-unittest.txt`
- `phase2-fastapi-smoke.txt`
- `phase2-go-api-connectivity.txt`
- `phase2-frontend-build.txt`
- `phase2-openspec-validate.txt`
- `phase2-docker-compose-config.txt`
- `phase3-python-unittest.txt`
- `phase3-fastapi-smoke.txt`
- `phase3-frontend-build.txt`
- `phase3-openspec-validate.txt`
- `phase3-docker-compose-config.txt`
- `phase4-python-unittest.txt`
- `phase4-fastapi-smoke.txt`
- `phase4-frontend-build.txt`
- `phase4-openspec-validate.txt`
- `phase4-docker-compose-config.txt`
- `phase45-python-unittest.txt`
- `phase45-fastapi-smoke.txt`
- `phase45-frontend-build.txt`
- `phase45-openspec-validate.txt`
- `phase45-docker-compose-config.txt`
- `phase5-python-unittest.txt`
- `phase5-frontend-build.txt`
- `phase5-openspec-validate.txt`
- `phase5-docker-compose-config.txt`
- `phase5-eval-summary.json`
- `phase6-python-unittest.txt`
- `phase6-frontend-build.txt`
- `phase6-openspec-validate.txt`
- `phase6-docker-compose-config.txt`
- `phase6-eval-summary.json`
- `phase6-fastapi-smoke.txt`
- `phase65-python-unittest.txt`
- `phase65-frontend-build.txt`
- `phase65-openspec-validate.txt`
- `phase65-docker-compose-config.txt`
- `phase65-eval-summary.json`

## 后续迭代

- 完整 MCP Server：可基于现有 Tool Registry 元数据暴露，但当前未实现。
- LLM 接入：Phase 6.5 已做可选总结润色节点；默认关闭，后续可继续扩展但不替代 Tool Calling 或 RAG。
- 向量数据库 RAG：知识库扩大后再考虑，当前是 Markdown 轻量检索。
- 持久化 Agent 工单状态：可从内存存储迁移到数据库，但 Agent 仍不直连 Go 服务背后的 PostgreSQL。

每个阶段开始前先更新 OpenSpec tasks/specs；每个阶段完成后同步更新 README、`docs/`、工程说明和验收证据。

## 已知限制

- 当前 workflow 已使用 LangGraph 状态图；Phase 6.5 的 LLM summary 为可选能力，默认关闭。
- 当前 RAG 是轻量 Markdown 检索，不是向量数据库 RAG，RAG 本身不调用 LLM。
- 当前不是完整 MCP Server，只是可 MCP 化 Tool Registry。
- FastAPI 当前使用内存存储，服务重启后工单会清空。
- Go API 连通性依赖  go-account-transaction` 服务已启动。
- 对账工单的 `expected_balance` 必须能转换为整数；格式不可用时会升级人工并记录原因。
- 当前 `dialogue_context` 只保存当前工单内的用户输入和补参历史；不做长期记忆或跨工单记忆。
- 当前评估为固定离线 cases + FakeRegistry，不代表真实线上准确率或生产业务正确率。
