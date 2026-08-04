# 验证证据索引

本目录保存各阶段的测试、构建、OpenSpec 校验、Docker 检查、评估输出和脱敏 smoke 结果。

## 既有阶段

- `phase1-*`：初始 API、前端骨架和 deterministic workflow 证据
- `phase2-*`：Tool Registry、Go API 对接和 trace 证据
- `phase3-*`：LangGraph workflow 证据
- `phase4-*`：Markdown RAG 证据
- `phase45-*`：同工单 continue 证据
- `phase5-*`：离线评估证据
- `phase6-*`：最终工程收口证据
- `phase65-*`：可选 LLM Summary Node 与 DeepSeek 对齐证据

## Phase 6.5 重点证据

- `phase65-python-unittest.txt`
- `phase65-frontend-build.txt`
- `phase65-openspec-validate.txt`
- `phase65-docker-compose-config.txt`
- `phase65-eval-summary.json`
- `phase65-deepseek-real-smoke.txt`

说明：

- `phase65-deepseek-real-smoke.txt` 是一次脱敏的真实模型 smoke
- 它只证明可选 `llm_summarize` 节点可以在启用配置后触发 `llm_call`
- 它不代表线上生产验证，也不代表模型效果承诺

## Phase 7 容器化升级证据

- `phase7-python-unittest.txt`
  - `cd D:\finance-ticket-agent\agent-api; python -m unittest discover -s tests -v`

- `phase7-frontend-build.txt`
  - `cd D:\finance-ticket-agent\frontend; npm run build`

- `phase7-openspec-validate.txt`
  - `cd D:\finance-ticket-agent; openspec validate --all --strict`

- `phase7-docker-compose-config.txt`
  - `cd D:\finance-ticket-agent; docker compose config`

- `phase7-docker-api-build.txt`
  - `cd D:\finance-ticket-agent; docker compose build agent-api`

- `phase7-docker-frontend-build.txt`
  - `cd D:\finance-ticket-agent; docker compose build frontend`

- `phase7-docker-smoke.txt`
  - `docker compose up -d`
  - `GET http://127.0.0.1:8000/healthz`
  - `GET http://127.0.0.1:5173`
  - `POST /api/tickets` 创建报销规则工单
  - `docker compose down`

## 证据阅读建议

如果想快速判断仓库当前是否可复现，可以优先看：

1. `phase7-openspec-validate.txt`
2. `phase7-python-unittest.txt`
3. `phase7-frontend-build.txt`
4. `phase7-docker-compose-config.txt`
5. `phase7-docker-api-build.txt`
6. `phase7-docker-frontend-build.txt`
7. `phase7-docker-smoke.txt`

## 当前解释边界

- 证据用于工程验收和回归
- 离线 eval 指标不代表线上准确率
- Docker smoke 只代表本地环境中的容器可用性
- LLM smoke 只代表可选节点集成通过，不代表生产质量
