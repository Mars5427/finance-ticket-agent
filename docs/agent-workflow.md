# Agent Workflow

## 当前阶段说明

本文描述 Phase 6.5 workflow。当前已使用 LangGraph 状态图，加入真实 Markdown RAG，支持缺参追问后的同工单补参继续执行，并提供固定 cases 的离线评估指标；Phase 6.5 新增可选 LLM Summary Node，默认关闭，不使用向量数据库，不实现完整 MCP Server。线上工单路径复用 Phase 2 的 Tool Registry，把余额异常解释和对账异常定位落到真实 Go API 工具调用；离线评估路径使用 FakeRegistry 且显式禁用 LLM，保证本地稳定可重复。

## LangGraph 节点

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

缺参或 unsupported 工单会从 `check_missing_fields` 直接进入 `summarize`，不会执行 RAG 或 Go 工具。Phase 4.5 仅对 `needs_more_info` 工单支持同 `ticket_id` 补参继续执行，不做通用闲聊、长期记忆或跨工单记忆。

节点职责：

- `initialize_context`：构建工单上下文、ticket_id、dialogue_context、tool_history 和 trace；继续工单时会保留历史 trace，追加 `continue_ticket`、`metadata_patch_applied`、`dialogue_context_updated`，并把补参 message 写入当前工单内 dialogue_context。
- `classify`：分类为 reimbursement_policy、balance_anomaly、reconciliation_anomaly 或 unsupported。
- `check_missing_fields`：检查 account_id、observed_balance、expected_balance、time_range 等必填字段。
- `plan`：记录任务拆解步骤和候选工具。
- `retrieve_evidence`：检索 Markdown 知识库，返回 source、heading、snippet、score、chunk_id，并记录 `rag_retrieval` trace。
- `execute_tools`：通过 Tool Registry 调用 Go API，不直连数据库。
- `summarize`：基于 RAG evidence、tool_calls 和业务规则生成结构化 summary。
- `llm_summarize`：Phase 6.5 可选总结润色节点。默认 disabled；启用后只基于 deterministic summary、RAG evidence 和 tool_calls 生成受约束 JSON，总结失败时回退规则结果。
- `escalation_check`：统一判断工具失败、证据不足、对账差异和 unsupported。
- `finalize`：输出兼容 FastAPI 的 `TicketResponse`。

## Trace 字段

每条 trace event 包含：

- `id`：trace 事件 ID。
- `step`：LangGraph 节点或 continuation 阶段。
- `event_type`：事件类型，例如 `classification`、`missing_parameters`、`rag_retrieval`、`tool_call`、`human_escalation`。
- `payload`：结构化上下文，例如缺失字段、工具参数、工具返回、RAG snippets、升级原因。
- `elapsed_ms`：相对本次 workflow 启动的耗时。
- `error`：失败时的错误信息。
- `created_at`：事件创建时间。

Phase 6.5 新增 LLM trace：
- `llm_skipped`：未启用 LLM、provider disabled 或缺少 Key/model/base_url 时记录，保留 deterministic summary。
- `llm_call`：模型成功返回合法 JSON 时记录，只包含 provider、model、prompt_version、elapsed_ms、输入/输出 summary 长度和 confidence。
- `llm_fallback`：模型请求失败、返回非法 JSON 或缺字段时记录，保留 deterministic summary。

trace 不保存 API Key、敏感 header 或完整 prompt。LLM 不能改写 tool_calls、evidence、ticket_type、metadata，也不能把 deterministic `needs_human=true` 改成 false。

## Phase 6.5 LLM Summary Node

`llm_summarize` 节点位于 `summarize` 之后、`escalation_check` 之前。Prompt 版本为 `finance_ticket_summary_v1`，输入包括 ticket_type、title、description、metadata、deterministic summary、RAG evidence snippets、tool_calls、needs_human 和 escalation_reason。

节点边界：
- 默认关闭，无 Key 时项目仍可完全本地运行。
- LLM 只负责让处理结论更自然、更结构化。
- 工具调用和 RAG evidence 仍是事实来源。
- Prompt 明确禁止编造制度、余额、流水或交易。
- 模型失败、无依据、业务冲突时保留规则结果或人工升级。
- 这不是完整聊天系统、长期记忆、跨工单记忆、完整 MCP Server 或向量数据库 RAG。

## RAG 检索

知识库文件：

- `knowledge/reimbursement-policy.md`
- `knowledge/approval-rules.md`
- `knowledge/reconciliation-sop.md`

检索方式：

- Markdown 按标题/段落切 chunk。
- chunk 字段为 source、heading、content、chunk_id。
- 检索使用关键词/token overlap/BM25-like scoring。
- 返回字段为 source、heading、snippet、score、chunk_id。

Trace event：

```json
{
  "event_type": "rag_retrieval",
  "payload": {
    "query": "...",
    "matched_sources": ["reimbursement-policy.md"],
    "snippets": ["..."],
    "scores": [0.8],
    "elapsed_ms": 1,
    "no_evidence_reason": null
  }
}
```

## 同工单补参继续执行

Phase 4.5 新增 `POST /api/tickets/{ticket_id}/continue`。该接口只处理因为缺少 metadata 而进入 `needs_more_info` 的工单：

- 读取旧 ticket，保持 `ticket_id`、title 和 description 不变。
- 合并旧 metadata 与 `metadata_patch`。
- 把用户补参 message 追加到当前工单内 `dialogue_context`。
- 保留旧 trace，不丢失原始 `missing_parameters` 追问记录。
- 追加 `continue_ticket`、`metadata_patch_applied`、`dialogue_context_updated` trace。
- 重新运行 LangGraph workflow，并更新 status、result、tool_calls、evidence 和 updated_at。

示例 trace：

```json
{
  "event_type": "metadata_patch_applied",
  "payload": {
    "metadata_patch": {"account_id": "demo-account", "observed_balance": 1500},
    "merged_metadata": {"account_id": "demo-account", "observed_balance": 1500}
  }
}
```

边界：这只是轻量多轮任务状态保持。`dialogue_context` 只保存当前工单内的原始用户输入和补参历史，不做完整聊天系统、长期记忆或跨工单记忆。

## 离线评估

Phase 5 新增 `agent-api/app/evaluation/runner.py` 和 `agent-api/scripts/run_eval.py`。评估不会修改 LangGraph 业务节点，而是批量读取 `eval_cases/finance_tickets.json` 中的固定工单：

- 构造 `TicketCreateRequest`。
- 使用 `EvaluationFakeRegistry` 注入稳定的账户、流水、交易详情和对账核验结果。
- 对带 `continue_request` 的 case，先得到 `needs_more_info`，再用同一个 ticket id 继续执行。
- 对 `rag_mode=force_no_evidence` 的 case，仅在评估 runner 内临时替换检索结果，验证无依据时不会编造回答。
- 从最终 `TicketResponse` 的 `status`、`result.tool_calls`、`result.evidence`、`trace` 和 `needs_human` 计算指标。

输出指标：

```json
{
  "total_cases": 12,
  "task_completion_rate": 0.4167,
  "status_match_rate": 1.0,
  "average_tool_call_count": 1.3333,
  "human_escalation_ratio": 0.5,
  "rag_evidence_coverage": 0.9,
  "continuation_success_rate": 1.0,
  "failure_type_distribution": {
    "missing_parameters": 1,
    "internal_reconciliation_mismatch": 1,
    "invalid_expected_balance": 1
  }
}
```

这些数字来自当前固定 eval cases，只用于工程验收和本地质量回归，不代表线上准确率、真实财务业务质量或模型效果。

## 三类工单

### 报销规则问答

典型问题：

- “出差餐补能报多少？”
- “打车费用没有发票可以报销吗？”

当前流程：

```text
分类 -> 缺参检查 -> retrieve_evidence(reimbursement-policy, approval-rules) -> 依据片段汇总 -> 结构化回答 -> 人工升级判断
```

人工升级条件：

- 知识库未检索到足够依据
- 规则冲突
- 用户问题涉及未覆盖制度

### 余额异常解释

典型问题：

- “账户余额为什么比我预期少 500？”

必填 metadata：

```json
{
  "account_id": "uuid",
  "observed_balance": 1500
}
```

当前流程：

```text
分类
  -> 检查 account_id/observed_balance
  -> retrieve_evidence(reconciliation-sop，可选)
  -> get_account
  -> list_account_transactions
  -> 有 transfer_id 时 get_transaction_detail
  -> 比较观察余额与账面余额
  -> 汇总差异解释
  -> 工具失败时人工升级
```

余额异常如果检索不到强相关 SOP，不会强行编造依据，只在 summary 中说明知识库没有强相关异常处理依据。

工具调用路径：

- `get_account` 获取账面余额。
- `list_account_transactions` 获取流水。
- `get_transaction_detail` 在流水中存在 `transfer_id` 时补充交易详情。

人工升级路径：

- Go 工具失败。
- 账户或流水数据缺失到无法解释。
- 输入字段不完整时先进入 `needs_more_info`，不直接升级。

### 对账异常定位

典型问题：

- “这个账户本月对账差了 1000，帮我定位原因。”

必填 metadata：

```json
{
  "account_id": "uuid",
  "expected_balance": 3000,
  "time_range": "2026-08"
}
```

当前流程：

```text
分类
  -> 检查 account_id/time_range/expected_balance
  -> retrieve_evidence(reconciliation-sop)
  -> list_account_transactions
  -> check_account_reconciliation
  -> 比较 expected_balance 与 current_balance
  -> 根据 matched/issues/evidence 汇总定位结论
  -> mismatch 或工具失败时人工升级
```

对账判断是两层：

- Go 内部一致：`current_balance` 与 `latest_ledger_balance_after` 一致。
- 外部预期一致：用户 `metadata.expected_balance` 与 `current_balance` 一致。

如果内部一致但外部预期不一致，系统会说明“内部账户与流水一致，但与外部对账单或用户预期余额不一致”，计算差额，并结合 SOP evidence 建议人工复核外部对账单来源、时间范围或入账延迟。`expected_balance` 格式无法转换为整数时，不继续推断，直接升级人工。

人工升级路径：

- Go `matched=false`，说明内部账户与流水不一致。
- Go 内部一致但用户 `expected_balance` 与 `current_balance` 不一致。
- `expected_balance` 无法转换为整数。
- 工具失败或 SOP 依据不足。

## 结构化输出

当前返回字段：

```json
{
  "ticket_type": "reconciliation_anomaly",
  "status": "escalated",
  "summary": "...",
  "evidence": [
    {
      "source": "reconciliation-sop.md",
      "heading": "基本步骤",
      "snippet": "确认账户、币种、时间范围和期望金额。",
      "score": 0.72,
      "chunk_id": "reconciliation-sop.md#2"
    }
  ],
  "tool_calls": [],
  "needs_human": true,
  "escalation_reason": "..."
}
```

## Phase 6.5 边界

Phase 6.5 只新增可选 LLM Summary Node。当前项目不依赖 LLM 才能运行，不宣称向量数据库 RAG、完整 MCP Server、完整多轮聊天、长期记忆、跨工单记忆、新业务工单类型或线上准确率。默认无 Key 时使用 deterministic fallback；启用 LLM 时也只润色结构化结论，不访问业务数据，不覆盖人工升级边界。Phase 6.5 完成后暂停。
