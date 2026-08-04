# 工程决策说明

本文记录项目关键设计决策、边界说明和常见问题，便于后续维护、代码审查和功能扩展。

## 项目边界

- 这是财务工单 Agent，不是泛聊天机器人。
- 这是 AI 全栈项目，不是生产财务系统。
- 第一版只做三类任务：报销规则问答、余额异常解释、对账异常定位。
- Agent 只通过 Tool Calling 访问 Go 业务服务，不直连 PostgreSQL。
- 当前已完成 Phase 5：FastAPI + LangGraph workflow + Markdown RAG + React 工作台 + MCP 风格 Tool Registry + Go API 对接 + 缺参追问后的同工单补参继续执行 + 固定 cases 离线评估指标。
- 当前还不能说已经完成向量数据库 RAG、依赖 LLM 的事实回答生成、完整 MCP Server、完整多轮聊天系统、长期记忆、跨工单记忆或线上准确率评估。

## Phase 4 设计说明

Phase 4 的重点是把 Phase 3 的 evidence 占位替换成真实 Markdown RAG。

实现方式：

- `knowledge/` 下维护报销制度、审批标准、对账异常 SOP。
- Markdown ingestion 按标题和段落切 chunk。
- 每个 chunk 保存 `source`、`heading`、`content`、`chunk_id`。
- 检索使用关键词/token overlap/BM25-like scoring。
- 返回 `source`、`heading`、`snippet`、`score`、`chunk_id`。
- LangGraph 新增 `retrieve_evidence` 节点，并记录 `rag_retrieval` trace。

三类工单：

- 报销规则问答必须检索 reimbursement policy 和 approval rules，并带 evidence snippets。
- 对账异常定位检索 reconciliation SOP，用于解释人工复核建议。
- 余额异常可检索异常处理 SOP；无强相关依据时不编造。

## Phase 4.5 设计说明

Phase 4.5 的重点是补上缺参追问后的同工单继续执行，而不是另起一个新工单。

实现方式：

- 新增 `TicketContinueRequest`，包含 `message` 和 `metadata_patch`。
- 新增 `POST /api/tickets/{ticket_id}/continue`，只允许继续 `needs_more_info` 工单。
- API 读取旧 ticket，合并 metadata，保留原 title、description、ticket_id 和 created_at。
- LangGraph `initialize_context` 识别 continuation，保留旧 trace，追加 `continue_ticket`、`metadata_patch_applied`、`dialogue_context_updated`。
- 补参 message 追加到当前工单内 `dialogue_context`，重新运行 workflow 后更新 status、tool_calls、evidence、summary 和 updated_at。

边界：

- 这是轻量多轮任务状态保持，不是完整多轮聊天。
- 不做长期记忆，不做跨工单记忆。
- `dialogue_context` 只保存当前工单内的原始输入和补参历史。

## Phase 5 设计说明

Phase 5 的重点是把“能跑 demo”推进到“能用固定样例做工程验收”。它不是线上准确率评估，也不是模型效果评测。

实现方式：

- `eval_cases/finance_tickets.json` 维护 12 条固定工单。
- 覆盖报销规则问答、余额异常解释、对账异常定位三类任务。
- 覆盖正常完成、缺参、continue 后完成、RAG 无依据、工具失败、expected_balance mismatch 和 unsupported。
- `agent-api/app/evaluation/runner.py` 调同一套 LangGraph workflow。
- 评估使用 `EvaluationFakeRegistry`，不依赖真实 Go 服务，不直连 PostgreSQL。
- `agent-api/scripts/run_eval.py` 输出 JSON summary。

指标：

- `total_cases`
- `task_completion_rate`
- `status_match_rate`
- `average_tool_call_count`
- `human_escalation_ratio`
- `rag_evidence_coverage`
- `continuation_success_rate`
- `failure_type_distribution`

`failure_type_distribution` 会细分无依据、工具失败、缺参、外部 expected_balance 不一致、内部对账不一致、expected_balance 格式不可用、unsupported、状态不匹配和类型不匹配。

边界说明：这些指标只来自固定 eval cases，用于工程验收和本地质量回归，不代表真实线上准确率、财务业务质量或 LLM 效果。

## Phase 6.5 设计说明

Phase 6.5 新增的是可选 LLM Summary Node，而不是把项目改成依赖 LLM 的聊天机器人。分类、RAG、Tool Calling 和人工升级边界仍然由确定性 workflow 控制；`summarize` 节点先生成 deterministic summary，`llm_summarize` 只在配置了兼容 Chat Completions 的 API Key 时把结论润色成更自然的结构化 JSON。

实现抓手：
- 新增 `agent-api/app/llm/config.py`、`client.py`、`prompts.py`。
- 默认 `LLM_ENABLED=false`、`LLM_PROVIDER=disabled`，无 Key 可完整本地运行。
- DeepSeek smoke 推荐 `LLM_PROVIDER=deepseek`、`LLM_MODEL=deepseek-v4-flash`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_TIMEOUT_SECONDS=20`、`LLM_MAX_TOKENS=800`。
- Prompt 版本是 `finance_ticket_summary_v1`。
- Prompt 输入是 metadata、deterministic summary、RAG evidence 和 tool_calls。
- Prompt 约束模型不得编造制度、余额、流水或交易。
- 输出要求 JSON：`summary`、`needs_human`、`escalation_reason`、`confidence`。
- trace 记录 `llm_skipped`、`llm_call` 或 `llm_fallback`，不记录 API Key 或完整 prompt。
- LLM 不能把 deterministic `needs_human=true` 改成 false。

边界说明：LLM 只负责总结润色，不负责直接访问业务数据；事实来源仍是 Go API 工具返回和 Markdown RAG evidence。离线 eval 默认 disabled LLM，因此指标仍是固定 cases 的工程验收结果，不代表线上准确率或模型效果。

真实 DeepSeek smoke 已通过，可说明可选 LLM summary 节点在配置 Key 后能触发 `llm_call`；这只是本地集成 smoke，不是线上生产验证，也不代表模型效果指标。

## 关键为什么

为什么做财务工单：财务场景天然需要规则依据、数据核验、可追踪过程和人工升级，比闲聊更能体现 Agent 工程能力。

为什么只做三类任务：它们分别覆盖知识问答、业务数据解释和异常定位，能形成清晰的业务闭环，又不会扩张成不可控平台。

为什么不直连 PostgreSQL：Go 服务已经封装业务校验、事务、流水一致性和限流边界；Agent 直接查库会绕开这些边界，也会扩大数据暴露面。

为什么 Tool Calling：让 Agent 通过受控能力访问真实业务数据，工具调用能被 schema 校验、错误映射和 trace 审计。

为什么 RAG：报销规则和 SOP 不能靠模型自由发挥，RAG 让回答有来源、有片段、有分数，方便人工复核，降低凭空回答风险。

为什么不用向量数据库：第一版知识库很小，Markdown chunk + 轻量评分已经足够演示依据检索和 trace；引入向量库会增加部署复杂度，不符合当前 MVP 边界。

为什么 trace：财务场景不能只给最终答案，还要解释每一步基于什么数据、命中了哪些依据、调用了什么工具、失败在哪里。

为什么人工升级：当证据不足、规则冲突、数据缺失或工具失败时，升级比编造答案更可靠。

为什么 Phase 4.5 只做轻量补参：当前最核心的问题是缺参后不要重新建单，而是保留同一个 ticket 的上下文和 trace 继续执行。它解决的是财务工单的任务状态保持，不是泛聊天、长期记忆或跨工单记忆。

为什么做离线评估：项目需要可重复验证任务完成状态、平均工具调用次数和人工升级比例，因此使用固定样例和可重复脚本支撑质量回归。用 FakeRegistry 是为了让评估稳定，不受本机 Go 服务状态影响。

## 项目说明

### 项目概览

这是一个面向财务工单的 AI 全栈 Agent 项目，只覆盖报销规则问答、余额异常解释和对账异常定位三类任务。后端用 FastAPI + LangGraph 把分类、缺参、RAG 检索、Tool Calling、总结和人工升级做成显式 workflow；工具层通过可 MCP 化 Tool Registry 调 Go 账户交易服务，不让 Agent 直连 PostgreSQL。前端用 React/TypeScript 展示工单列表、执行步骤、工具参数和返回、RAG evidence、补参 trace 和结论。最后用 12 条固定 eval cases 做离线评估，输出完成率、平均工具调用次数、人工升级比例和失败类型分布。

### 架构说明

这个项目的核心不是做一个泛聊天机器人，而是把财务工单处理做成可审计的 Agent Workflow。报销类问题走 Markdown RAG，回答必须带制度或审批依据；余额异常走 Go 工具查询账户、流水和交易详情；对账异常会调用流水和 reconciliation 工具，并额外比较用户传入的 expected_balance，区分内部账实不一致和外部对账单口径不一致。

工程上我先用 FastAPI 建工单 API，再用 LangGraph 显式拆出 initialize、classify、check_missing_fields、plan、retrieve_evidence、execute_tools、summarize、escalation_check、finalize。所有 RAG 检索、工具调用、缺参追问、continue 补参和人工升级都会写入 trace。Phase 5 增加离线评估脚本，用 FakeRegistry 跑 12 条固定 cases，避免依赖真实 Go 服务状态，也不把这些数字说成线上准确率。

### 设计深潜

从业务边界看，Agent 只处理三类财务工单，分别覆盖知识问答、业务数据解释和异常定位。报销规则需要依据，余额解释需要真实账户和流水，对账定位需要内部 reconciliation 与外部 expected_balance 两层判断。这个组合能完整展示 RAG、Tool Calling、LangGraph、trace、前端工作台和评估链路。

从系统边界看，Agent 不直连数据库，而是通过 Tool Registry 调 Go HTTP API。Go 服务继续拥有账户、流水、交易、对账核验、事务和 Redis 限流边界；Agent 只拿到受控工具返回，并把每次调用参数、输出、耗时和错误写入 trace。Tool Registry 目前不是完整 MCP Server，但已经按 MCP 化方向维护 name、description、input schema、output schema、handler 和 error mapping。

从可靠性看，系统遇到缺参会追问，查不到 RAG 依据不会编造，工具失败会升级人工，对账内部或外部余额冲突也会升级人工。评估脚本读取固定 cases，统计 task_completion_rate、average_tool_call_count、human_escalation_ratio 和 failure_type_distribution，用于工程验收和本地质量回归，不代表线上准确率。

Q：Phase 4 最大价值是什么？

A：Phase 4 把报销和 SOP 的依据从占位改成了真实 Markdown RAG。workflow 会检索知识库 chunk，返回 source、heading、snippet、score，并把 query、命中来源、片段、分数和 no_evidence_reason 写入 trace。这样回答不是凭空生成，而是可以被前端展示和人工复核。

Q：查不到依据怎么办？

A：不会编造。报销规则问答查不到足够依据时会明确说明知识库未命中，并升级人工；余额异常如果 SOP 不强相关，只说明没有额外 SOP 依据；对账异常会优先基于工具结果，并说明是否有 SOP 支撑。

Q：为什么不让 Agent 直接查数据库？

A：数据库不是 Agent 的能力边界。Go 服务已经维护账户、流水、交易详情、对账核验、事务和限流。Agent 只调 Go HTTP API，可以保留业务校验，也能把每次工具调用完整记录到 trace。

Q：现在是不是已经有 MCP？

A：还不是完整 MCP Server。当前实现的是可 MCP 化工具层：每个工具都有 name、description、input schema、output schema、handler 和错误映射。这样后续暴露成 MCP Server 时不需要推翻工具契约。

Q：Phase 4.5 的 ticket continue 和多轮聊天有什么区别？

A：ticket continue 只服务缺参工单。用户补充 `metadata_patch` 后，系统在同一个 ticket_id 上合并参数、追加当前工单内 dialogue_context、保留旧 trace 并重新运行 LangGraph。它不回答闲聊，不做长期记忆，也不会把一个工单的信息带到另一个工单。

Q：Phase 5 的评估指标怎么来的？

A：来自 `eval_cases/finance_tickets.json` 的 12 条固定离线工单，不依赖真实 Go 服务。runner 用 FakeRegistry 调同一套 LangGraph workflow，然后统计完成状态、工具调用、人工升级、RAG evidence、continue 成功和失败类型。这些指标是工程验收证据，不是线上准确率。

Q：为什么需要 Tool Calling？

A：财务工单不能靠模型猜账户余额或流水。Tool Calling 把 Agent 能访问的业务能力收敛成受控工具，输入输出有 schema，失败有错误映射，调用过程能进 trace。

Q：为什么是可 MCP 化而不是完整 MCP Server？

A：当前项目目标是体现工具契约和边界，不需要引入完整 MCP Server 的部署复杂度。现在工具已经有 name、description、input schema、output schema、handler 和 error mapping，后续要暴露 MCP Server 可以复用这层。

Q：Go 服务在项目里承担什么角色？

A：Go 服务是业务数据后端，负责账户、流水、交易详情和对账核验。Agent 通过 HTTP 工具调用它，而不是绕开服务直接查库，这样保留业务校验、事务边界和审计路径。

Q：这个项目和普通 CRUD 后端有什么区别？

A：普通 CRUD 更关注资源增删改查。这个项目关注工单处理流程：分类、缺参追问、RAG evidence、工具选择、工具执行、结构化总结、人工升级、trace 和离线评估，强调的是 Agent 后端编排和可解释性。

Q：Phase 6.5 为什么只做 LLM Summary Node？

A：因为当前项目的事实来源已经很清楚：财务制度来自 Markdown RAG，账户/流水/对账数据来自 Go API Tool Calling。LLM 最适合在这个阶段做受约束的结论润色，而不应该接管分类、工具调用或证据判断。这样既能体现 Prompt 设计、结构化输出和失败 fallback，又不会破坏财务场景的可审计边界。

Q：没有 API Key 项目还能跑吗？

A：可以。默认 `LLM_ENABLED=false`、`LLM_PROVIDER=disabled`，workflow 会记录 `llm_skipped` 并保留 deterministic summary。单测、前端 build、OpenSpec validate、Docker config 和离线 eval 都不依赖外网模型。

Q：为什么加 `LLM_MAX_TOKENS`？

A：DeepSeek JSON Output 场景建议给出合理输出长度约束。这里默认 800，只限制总结节点的返回长度，避免模型输出过长或成本不可控；它不影响工具调用、RAG、分类，也不影响无 Key 的离线运行。

Q：模型输出错了怎么办？

A：如果 HTTP 请求失败、返回非法 JSON、缺少字段或 confidence 不合法，系统记录 `llm_fallback`，保留规则生成的 summary 和人工升级判断。如果规则已经判断需要人工升级，模型即使返回 `needs_human=false` 也不能取消升级。

Q：还有哪些后续迭代？

A：可以做完整 MCP Server、把 LLM 从可选总结扩展到更严格的可评估节点、在知识库扩大后引入向量检索、把 Agent 工单状态从内存迁移到持久化存储。但这些都不是当前 MVP，当前不夸大。
