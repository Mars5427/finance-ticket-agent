# Finance Ticket Agent

一个聚焦财务工单处理的全栈 Agent 工程项目。当前只覆盖三类工单：

- 报销规则问答
- 余额异常解释
- 对账异常定位

项目重点不是把系统做成泛聊天机器人，而是把财务工单处理流程做成可复现、可审计、可扩展的工程实现：FastAPI + LangGraph 负责编排，Go 账户交易系统提供真实业务数据，Markdown RAG 提供规则依据，React 工作台展示 trace、工具调用和处理结论。

## 当前能力

- LangGraph 工作流：分类、缺参追问、任务拆解、RAG 检索、工具调用、结构化总结、人工升级
- MCP 风格 Tool Registry：`get_account`、`list_account_transactions`、`get_transaction_detail`、`check_account_reconciliation`
- 真实 Markdown RAG：返回 `source`、`heading`、`snippet`、`score`、`chunk_id`
- 同工单补参继续执行：`POST /api/tickets/{ticket_id}/continue`
- React 工作台：工单创建、列表、详情、工具调用、依据片段、trace
- 离线评估：固定 12 条 cases，输出完成率、平均工具调用次数、人工升级比例和失败类型分布
- 可选 LLM Summary Node：默认关闭，无 Key 时完整本地运行；已支持脱敏的真实 DeepSeek smoke 证据
- Docker 化运行时：`agent-api` + `frontend` 两个服务可直接 `docker compose up --build`

## 技术栈

- Backend: Python, FastAPI, LangGraph
- Frontend: React, TypeScript, Vite
- Business backend: Go account transaction HTTP API
- Retrieval: local Markdown RAG
- Tooling: MCP-style Tool Registry, OpenSpec, Docker, Nginx

## 架构

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

`docker-compose.yml` 只编排本仓库自己的运行时：

- `agent-api`
- `frontend`

不会额外拉起：

- Go 账户交易服务
- Go 服务背后的 PostgreSQL
- Go 服务背后的 Redis

## 目录概览

```text
finance-ticket-agent/
├─ agent-api/                  # FastAPI + LangGraph + Tool Registry + RAG + eval
├─ frontend/                   # React workbench
├─ knowledge/                  # Markdown knowledge base
├─ eval_cases/                 # Fixed offline evaluation cases
├─ docs/                       # Design, API, workflow, engineering notes, evidence
├─ openspec/                   # Spec-driven change history
└─ docker-compose.yml
```

## 启动前准备

1. 启动外部 Go 账户交易系统。
2. 确认它可以通过 HTTP 访问。
3. 本仓库再选择裸机启动或 Docker 启动。

Go 服务单独启动示例：

```powershell
cd D:\Career_Research\go-account-transaction
docker compose up -d
```

默认情况下，本仓库中的 Agent API 会把 Go 服务地址视为：

```text
http://127.0.0.1:8080         # 裸机运行
http://host.docker.internal:8080  # Docker 运行默认值
```

## 裸机启动

### 1. 启动 Agent API

```powershell
cd D:\finance-ticket-agent\agent-api
$env:GO_ACCOUNT_API_BASE_URL="http://127.0.0.1:8080"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 2. 启动前端

```powershell
cd D:\finance-ticket-agent\frontend
npm install
npm run dev
```

### 3. 访问

- 前端工作台：`http://127.0.0.1:5173`
- FastAPI docs：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/healthz`

## Docker 启动

### 1. 先启动外部 Go 服务

本仓库的 Compose 不会帮你启动 Go 服务。

### 2. 可选配置 LLM 环境变量

默认不需要配置，系统会走 deterministic summary。

如需启用可选 LLM Summary Node，可在当前终端设置：

```powershell
$env:LLM_ENABLED="true"
$env:LLM_PROVIDER="deepseek"
$env:LLM_API_KEY="<redacted>"
$env:LLM_MODEL="deepseek-v4-flash"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_TIMEOUT_SECONDS="20"
$env:LLM_MAX_TOKENS="800"
```

### 3. 启动容器

```powershell
cd D:\finance-ticket-agent
docker compose up --build
```

### 4. 访问

- 前端工作台：`http://127.0.0.1:5173`
- FastAPI docs：`http://127.0.0.1:8000/docs`
- Agent API 健康检查：`http://127.0.0.1:8000/healthz`

### 5. 停止容器

```powershell
docker compose down
```

## Docker 的意义

- 固化 Python / Node / Nginx 运行环境
- 降低本地复现成本
- 让前后端联调方式更接近真实部署
- 把前端 `/api` 代理和后端运行参数收敛到一处

当前仍然使用内存存储保存 Agent 工单、`dialogue_context` 和 trace，因此服务重启后工单会清空。后续如果要做更接近生产的部署，可以把 Agent 状态迁移到 PostgreSQL，并把 Redis 用于缓存、限流、短期状态或异步任务协调，但这不在当前仓库范围内。

## 关键 API

- `POST /api/tickets`
- `GET /api/tickets`
- `GET /api/tickets/{ticket_id}`
- `GET /api/tickets/{ticket_id}/trace`
- `POST /api/tickets/{ticket_id}/continue`
- `GET /api/tools`
- `GET /healthz`

示例：创建一条余额异常工单

```powershell
$body = @{
  title = "余额异常解释"
  description = "账户余额比我预期少 500，帮我解释一下。"
  metadata = @{ account_id = "demo-account"; observed_balance = 1500 }
} | ConvertTo-Json -Depth 10

$body | curl.exe -s -X POST http://127.0.0.1:8000/api/tickets `
  -H "Content-Type: application/json" `
  --data-binary '@-'
```

示例：继续处理缺参工单

```powershell
$body = @{
  message = "账户是 demo-account，我看到的余额是 1500"
  metadata_patch = @{ account_id = "demo-account"; observed_balance = 1500 }
} | ConvertTo-Json -Depth 10

$body | curl.exe -s -X POST http://127.0.0.1:8000/api/tickets/<ticket-id>/continue `
  -H "Content-Type: application/json" `
  --data-binary '@-'
```

更多接口说明见 [docs/api.md](docs/api.md)。

## 离线评估

评估不依赖真实 Go 服务，也不依赖真实 LLM。

```powershell
cd D:\finance-ticket-agent\agent-api
python scripts\run_eval.py
```

保存结果：

```powershell
python scripts\run_eval.py --output ..\docs\evidence\phase6-eval-summary.json
```

输出指标包括：

- `total_cases`
- `task_completion_rate`
- `status_match_rate`
- `average_tool_call_count`
- `human_escalation_ratio`
- `rag_evidence_coverage`
- `continuation_success_rate`
- `failure_type_distribution`

这些指标来自固定 cases，只用于工程验收和回归，不代表线上准确率。

## 证据文件

验证证据集中保存在 [docs/evidence/README.md](docs/evidence/README.md)。

当前重点文件包括：

- `phase6-eval-summary.json`
- `phase65-deepseek-real-smoke.txt`
- `phase7-python-unittest.txt`
- `phase7-frontend-build.txt`
- `phase7-openspec-validate.txt`
- `phase7-docker-compose-config.txt`
- `phase7-docker-api-build.txt`
- `phase7-docker-frontend-build.txt`
- `phase7-docker-smoke.txt`

## 当前边界

- 只覆盖三类财务工单，不扩展新工单类型
- RAG 是本地 Markdown 检索，不是向量数据库
- 不是完整 MCP Server，只是 MCP 风格 Tool Registry
- 不是完整多轮聊天、长期记忆或跨工单记忆
- 可选 LLM 只负责总结润色，不负责业务事实获取
- LLM 默认关闭，无 Key 时仍可完整本地运行
- 当前未实现 LLM metadata extraction 节点；如需加入，会保持默认关闭且只补全缺失字段
- Docker build 依赖从 Docker Hub 拉取基础镜像；如果运行环境无法访问 `docker.io`，compose build 和 runtime smoke 会被外部网络阻塞，详见 `docs/evidence/phase7-docker-*.txt`

## 后续迭代

- Agent 状态持久化
- 更完整的 MCP Server 暴露
- 更系统的评估数据集与回归策略
- 在知识库规模扩大后再考虑向量检索
- 低风险前提下增加可选 LLM metadata extraction
