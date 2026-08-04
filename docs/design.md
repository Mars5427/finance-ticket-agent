# 设计文档

## 项目目标

这个项目聚焦三个财务工单场景：

- 报销规则问答
- 余额异常解释
- 对账异常定位

目标不是做一个泛聊天系统，而是把财务工单处理拆成一条可检查、可追踪、可本地复现的工程链路：分类、缺参追问、RAG 检索、Tool Calling、结构化结论、人工升级、前端可视化和固定 cases 评估。

## 系统架构

```text
Browser
  -> React workbench
      -> /api proxied to FastAPI Agent API
          -> LangGraph workflow
              -> Markdown RAG
              -> MCP-style Tool Registry
                  -> external Go account transaction HTTP API
                      -> PostgreSQL / Redis owned by the Go service
```

当前仓库中的 `docker-compose.yml` 只编排：

- `agent-api`
- `frontend`

它不会编排：

- Go 账户交易系统
- Go 服务背后的 PostgreSQL
- Go 服务背后的 Redis

## 运行模式

### 裸机模式

- FastAPI 直接监听 `127.0.0.1:8000`
- Vite dev server 监听 `127.0.0.1:5173`
- Vite 开发代理把 `/api` 转发到 FastAPI

### Docker 模式

- `agent-api` 容器运行 FastAPI + LangGraph
- `frontend` 容器运行 Nginx，托管 React 构建产物
- Nginx 把 `/api` 和 `/healthz` 代理到 `agent-api`
- `agent-api` 通过 `GO_ACCOUNT_API_BASE_URL` 连接外部 Go 服务，默认 `http://host.docker.internal:8080`

Docker 化的意义：

- 固化 Python / Node / Nginx 运行环境
- 降低本地复现成本
- 让前后端集成方式更接近部署形态

## Agent Workflow

当前 LangGraph 节点顺序：

```text
initialize_context
  -> classify
  -> check_missing_fields
  -> plan
  -> retrieve_evidence
  -> execute_tools
  -> summarize
  -> llm_summarize (optional)
  -> escalation_check
  -> finalize
```

节点职责：

- `initialize_context`：构建 `ticket_id`、`metadata`、`dialogue_context`、`tool_history` 和 trace
- `classify`：判断三类支持工单或 `unsupported`
- `check_missing_fields`：检查必填字段并生成追问
- `plan`：记录任务拆解和候选工具
- `retrieve_evidence`：执行 Markdown RAG
- `execute_tools`：通过 Tool Registry 调 Go HTTP API
- `summarize`：生成确定性结构化结论
- `llm_summarize`：可选总结润色，默认关闭
- `escalation_check`：统一判断人工升级
- `finalize`：输出 `TicketResponse`

## Tool Registry 边界

Tool Registry 采用 MCP 风格定义，但当前并不是完整 MCP Server。

每个工具包含：

- `name`
- `description`
- `input_schema`
- `output_schema`
- `handler`
- `error mapping`

当前工具：

- `get_account`
- `list_account_transactions`
- `get_transaction_detail`
- `check_account_reconciliation`

Agent 只允许通过这些工具访问业务数据，不允许直连 PostgreSQL。

## Go 服务边界

Go 服务继续承担：

- 账户查询
- 流水检索
- 交易详情
- 对账核验
- 自己的事务、一致性和 Redis 相关边界

这样设计的原因：

- 业务校验留在业务服务内
- Agent 的能力面保持受控
- trace 能完整记录工具调用输入、输出、耗时和错误

## RAG 设计

知识库文件：

- `knowledge/reimbursement-policy.md`
- `knowledge/approval-rules.md`
- `knowledge/reconciliation-sop.md`

实现方式：

- 按 Markdown 标题和段落切 chunk
- chunk 字段：`source`、`heading`、`content`、`chunk_id`
- 检索方式：关键词 / token overlap / BM25-like scoring
- 返回字段：`source`、`heading`、`snippet`、`score`、`chunk_id`

这不是向量数据库 RAG，也不依赖 LLM。

## 三类工单路径

### 报销规则问答

```text
classify
  -> check_missing_fields
  -> retrieve_evidence(reimbursement-policy, approval-rules)
  -> summarize
  -> escalation_check
```

要求：

- 回答必须带依据片段
- 无依据时不编造，必要时人工升级

### 余额异常解释

必填 metadata：

- `account_id`
- `observed_balance`

路径：

```text
classify
  -> check_missing_fields
  -> retrieve_evidence(reconciliation-sop, optional)
  -> get_account
  -> list_account_transactions
  -> get_transaction_detail (when transfer_id exists)
  -> summarize
  -> escalation_check
```

### 对账异常定位

必填 metadata：

- `account_id`
- `expected_balance`
- `time_range`

路径：

```text
classify
  -> check_missing_fields
  -> retrieve_evidence(reconciliation-sop)
  -> list_account_transactions
  -> check_account_reconciliation
  -> summarize
  -> escalation_check
```

判断分两层：

1. Go 内部一致性：`current_balance` vs `latest_ledger_balance_after`
2. 外部预期一致性：`current_balance` vs `metadata.expected_balance`

如果内部一致但外部预期不一致，仍然升级人工。

## 同工单 continue

`POST /api/tickets/{ticket_id}/continue` 只支持缺参工单继续执行。

它会：

- 保留同一个 `ticket_id`
- 合并旧 `metadata` 和 `metadata_patch`
- 追加当前工单内 `dialogue_context`
- 保留旧 trace 并追加 continuation 事件
- 重新执行 LangGraph

这属于轻量任务状态保持，不是完整聊天系统、长期记忆或跨工单记忆。

## LLM 设计

当前只实现了可选 `llm_summarize` 节点：

- 默认关闭
- 只基于 deterministic summary、tool outputs、RAG evidence 生成更自然的结构化总结
- 不改写工具结果、evidence、ticket type、metadata
- 不允许把 deterministic `needs_human=true` 改成 false

支持环境变量：

- `LLM_ENABLED`
- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_BASE_URL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_TOKENS`

当前没有实现 LLM metadata extraction 节点。本轮只把这件事保留为后续低风险增强方向。

## 状态与存储

Agent API 当前仍然使用内存存储：

- 工单
- 当前工单内 `dialogue_context`
- trace

服务重启后数据会清空。后续如需更接近真实部署，可以迁移到 PostgreSQL，并把 Redis 用于缓存、限流或异步协调，但这不在当前仓库范围内。

## 评估设计

`eval_cases/finance_tickets.json` 当前维护 12 条固定工单。

`agent-api/scripts/run_eval.py` 复用真实 LangGraph workflow，并通过 FakeRegistry 保持结果可重复。

指标包括：

- `task_completion_rate`
- `status_match_rate`
- `average_tool_call_count`
- `human_escalation_ratio`
- `rag_evidence_coverage`
- `continuation_success_rate`
- `failure_type_distribution`

这些数字只代表固定 cases 的工程验证结果，不代表线上准确率。
