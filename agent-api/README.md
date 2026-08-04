# agent-api

FastAPI + LangGraph backend for the finance ticket Agent.

## 负责内容

- 工单创建、查询、trace 查询、同工单 continue
- LangGraph workflow 编排
- MCP 风格 Tool Registry
- Go account transaction HTTP API 调用
- Markdown RAG
- 离线评估 runner
- 可选 LLM Summary Node

## 本地运行

```powershell
cd D:\finance-ticket-agent\agent-api
$env:GO_ACCOUNT_API_BASE_URL="http://127.0.0.1:8080"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Docker 运行

由仓库根目录的 compose 启动：

```powershell
cd D:\finance-ticket-agent
docker compose up --build agent-api
```

默认 Go 服务地址：

```text
http://host.docker.internal:8080
```

如需覆盖：

```powershell
$env:GO_ACCOUNT_API_BASE_URL="http://host.docker.internal:8080"
```

## 可选 LLM 配置

默认关闭，不配置 Key 也能完整运行测试、前端和离线评估。

```powershell
$env:LLM_ENABLED="true"
$env:LLM_PROVIDER="deepseek"
$env:LLM_API_KEY="<redacted>"
$env:LLM_MODEL="deepseek-v4-flash"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_TIMEOUT_SECONDS="20"
$env:LLM_MAX_TOKENS="800"
```

边界：

- LLM 只润色总结，不替代 Tool Calling 和 RAG
- 无 Key 时记录 `llm_skipped`
- 失败时记录 `llm_fallback`
- 成功时记录 `llm_call`
- 不记录 Key、Authorization header 或完整 prompt

## 测试

```powershell
cd D:\finance-ticket-agent\agent-api
python -m unittest discover -s tests -v
```

## 离线评估

```powershell
cd D:\finance-ticket-agent\agent-api
python scripts\run_eval.py
```

## 运行边界

- Agent 状态仍是内存存储
- 工单服务重启后数据会清空
- Agent 不直连 Go 服务背后的 PostgreSQL
- 当前没有 LLM metadata extraction 节点
