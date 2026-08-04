# Agent Workflow

## 节点顺序

当前 LangGraph workflow：

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

如果缺参或 `unsupported`，workflow 会在 `check_missing_fields` 后直接进入 `summarize`，不会执行 RAG 或业务工具。

## 节点职责

- `initialize_context`
  - 初始化 `ticket_id`
  - 构建 `dialogue_context`
  - 准备 `tool_history`
  - 写入首条 trace

- `classify`
  - 将工单分类为 `reimbursement_policy`
  - `balance_anomaly`
  - `reconciliation_anomaly`
  - `unsupported`

- `check_missing_fields`
  - 检查各工单类型的必填 metadata
  - 生成追问
  - 决定是否继续执行

- `plan`
  - 记录任务拆解步骤
  - 记录候选工具列表

- `retrieve_evidence`
  - 对 Markdown 知识库执行检索
  - 返回 `source`、`heading`、`snippet`、`score`、`chunk_id`
  - 写入 `rag_retrieval` trace

- `execute_tools`
  - 仅通过 Tool Registry 调用 Go HTTP API
  - 记录工具输入、输出、状态、耗时、错误

- `summarize`
  - 基于 evidence、tool_calls 和规则结果生成确定性 summary

- `llm_summarize`
  - 可选节点
  - 默认关闭
  - 只对 summary 做受约束润色
  - 失败时 fallback 到确定性 summary

- `escalation_check`
  - 判断是否需要人工升级
  - 统一处理工具失败、无依据、余额冲突、对账冲突和 unsupported

- `finalize`
  - 输出 `TicketResponse`

## 三类工单路径

### 报销规则问答

```text
classify
  -> check_missing_fields
  -> plan
  -> retrieve_evidence(reimbursement-policy, approval-rules)
  -> summarize
  -> llm_summarize(optional)
  -> escalation_check
  -> finalize
```

规则：

- 必须带依据片段
- 无足够依据时不编造
- 必要时人工升级

### 余额异常解释

必填：

- `account_id`
- `observed_balance`

路径：

```text
classify
  -> check_missing_fields
  -> plan
  -> retrieve_evidence(reconciliation-sop, optional)
  -> get_account
  -> list_account_transactions
  -> get_transaction_detail (when transfer_id exists)
  -> summarize
  -> llm_summarize(optional)
  -> escalation_check
  -> finalize
```

### 对账异常定位

必填：

- `account_id`
- `expected_balance`
- `time_range`

路径：

```text
classify
  -> check_missing_fields
  -> plan
  -> retrieve_evidence(reconciliation-sop)
  -> list_account_transactions
  -> check_account_reconciliation
  -> summarize
  -> llm_summarize(optional)
  -> escalation_check
  -> finalize
```

对账规则：

- 内部一致：`current_balance == latest_ledger_balance_after`
- 外部一致：`current_balance == expected_balance`
- 内部一致但外部不一致时仍升级人工
- `expected_balance` 非整数时直接升级人工

## 缺参 continue 路径

`POST /api/tickets/{ticket_id}/continue` 只支持 `needs_more_info` 工单。

继续执行时：

- 保留原 `ticket_id`
- 合并旧 `metadata` 与 `metadata_patch`
- 追加当前工单内 `dialogue_context`
- 保留旧 trace
- 追加：
  - `continue_ticket`
  - `metadata_patch_applied`
  - `dialogue_context_updated`

这只是轻量任务状态保持，不是完整聊天系统。

## Trace 字段

每条 trace event 包含：

- `id`
- `step`
- `event_type`
- `payload`
- `elapsed_ms`
- `error`
- `created_at`

常见事件：

- `classification`
- `missing_parameters`
- `task_decomposition`
- `rag_retrieval`
- `tool_call`
- `structured_output`
- `human_escalation`
- `ticket_finalized`
- `llm_skipped`
- `llm_call`
- `llm_fallback`

## LLM 边界

当前只实现了可选总结节点，没有实现 LLM metadata extraction。

`llm_summarize` 的约束：

- 只能基于 deterministic summary、RAG evidence、tool outputs
- 不得编造制度、余额、流水或交易
- 不能改写 tool_calls、evidence、ticket_type、metadata
- 不能把 deterministic `needs_human=true` 改成 false

后续如增加 metadata extraction，也会保持默认关闭，并且只补全缺失字段，不覆盖用户显式传入的 metadata。
