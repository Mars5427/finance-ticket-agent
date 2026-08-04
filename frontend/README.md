# frontend

React + TypeScript workbench for the finance ticket Agent.

## 负责内容

- 工单创建
- 工单列表与详情
- 处理结论展示
- RAG evidence 展示
- 工具调用结果展示
- trace 时间线展示
- `needs_more_info` 工单的同工单 continue 提交

## 本地运行

```powershell
cd D:\finance-ticket-agent\frontend
npm install
npm run dev
```

本地开发时由 Vite 代理：

- `/api` -> `http://127.0.0.1:8000`
- `/healthz` -> `http://127.0.0.1:8000`

## Docker 运行

由仓库根目录 compose 启动：

```powershell
cd D:\finance-ticket-agent
docker compose up --build frontend
```

容器运行时由 Nginx 托管静态页面，并把 `/api`、`/healthz` 代理到 `agent-api` 容器。

## 构建

```powershell
cd D:\finance-ticket-agent\frontend
npm run build
```
