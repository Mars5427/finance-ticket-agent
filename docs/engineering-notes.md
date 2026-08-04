# 工程说明

## 项目边界

- 这是财务工单 Agent，不是泛聊天机器人
- 只覆盖三类工单：报销规则问答、余额异常解释、对账异常定位
- Agent 不直连 Go 服务背后的 PostgreSQL
- 当前仓库不实现完整 MCP Server
- 当前 RAG 不是向量数据库
- 当前 Agent 状态仍是内存存储
- 可选 LLM 默认关闭
- 当前没有实现 LLM metadata extraction 节点

## 为什么保留 Go 服务为外部依赖

这个仓库把 Go 账户交易系统视为独立业务后端，而不是本仓库要“接管”的一部分。

这样做有几个直接好处：

- 账户、流水、交易详情、对账核验逻辑继续留在业务服务中
- Agent 的能力边界清晰，只能通过工具访问受控接口
- compose 不需要复制 Go 服务自己的数据库和缓存拓扑
- 前后端开发者可以更清楚地区分“Agent 编排层”和“业务数据层”

## 为什么这次优先做 Docker

在功能已经基本齐备之后，影响复现质量的主要瓶颈不是“再加一个新能力”，而是运行环境不固定：

- Python 依赖版本容易漂移
- 前端静态托管和 API 代理靠本地开发经验才能跑通
- 新读者不知道 Go 服务和 Agent 服务的边界

因此这次升级优先补齐：

- `agent-api/Dockerfile`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- 真实 `docker-compose.yml`

## Docker 化后的运行关系

```text
Browser
  -> frontend container (Nginx)
      -> /api, /healthz
          -> agent-api container (FastAPI)
              -> external Go HTTP API
```

Compose 只负责：

- `agent-api`
- `frontend`

不会负责：

- Go 服务
- PostgreSQL
- Redis

这不是遗漏，而是刻意设计。

## 为什么 Agent 不直连数据库

- Go 服务已经封装业务校验和一致性语义
- Tool Calling 的 trace 更容易做审计
- 避免让 Agent 获得过宽的数据访问面
- 保持业务层和编排层职责清晰

## 为什么当前仍然用内存存储

当前目标是让仓库更完整、可复现、可扩展，而不是立刻把部署复杂度做满。

内存存储的代价很明确：

- FastAPI 重启后工单会丢失

但它也让仓库在当前阶段保持：

- 依赖少
- 本地运行快
- 结构清楚
- 更容易把注意力放在 workflow、RAG、Tool Calling 和 trace 上

如果以后要向长期运行场景靠近，比较自然的升级方向是：

- PostgreSQL 保存工单与 trace
- Redis 做缓存、限流、短期状态或异步协调

## 为什么 RAG 先不用向量数据库

当前知识库文件数量很少，Markdown 按标题和段落切 chunk 后，用轻量关键词 / token overlap / BM25-like scoring 已经能满足：

- 报销制度引用
- 审批标准引用
- 对账 SOP 引用
- trace 可回放

过早引入向量数据库只会把部署和调试复杂度拉高。

## 为什么 LLM 只做可选总结

当前系统的事实来源已经比较明确：

- 业务事实来自 Go API 工具返回
- 规则依据来自 Markdown RAG

所以最合适的 LLM 接入点，是在确定性结果之后做一个受约束的总结节点：

- 有 Key 时可以让结论更自然
- 无 Key 时项目仍然完整可跑
- 失败时可以回退
- 不破坏 Tool Calling 和 RAG 的事实边界

## 为什么这轮没有强行做 LLM metadata extraction

它是一个合理的后续增强点，但不是这轮的第一优先级。

原因很实际：

- 容器化直接提升仓库复现质量
- metadata extraction 会改变缺参路径，回归面更大
- 当前 deterministic 缺参追问已经能闭环

所以这轮只把 metadata extraction 作为 OpenSpec 里的可选增强边界保留下来，不强行落地。

## 当前已落地的质量抓手

- OpenSpec change + strict validate
- Python 单元测试
- 前端构建
- Docker compose config
- Docker build
- Docker runtime smoke
- 固定 eval cases
- 可选 LLM 的脱敏 smoke evidence

## 常见问题

### 为什么不是完整 MCP Server？

当前项目已经有 MCP 风格 Tool Registry，但还没有把它暴露成完整 MCP Server。这样可以先把工具契约、错误映射和 trace 做扎实，再决定是否增加额外的部署复杂度。

### 为什么不把 Go 服务也写进这个 compose？

因为当前目标是让本仓库自己的运行时完整，而不是把另一个业务系统重新打包一遍。Go 服务有自己的源码、数据平面和启动方式，本仓库只定义它的访问边界。

### Docker 化之后是不是就更接近生产？

更接近部署形态，但不等于生产系统。当前仍然是内存存储，当前指标也仍然是固定离线 cases，不代表线上准确率。

### 如果 Docker build 在当前环境失败，最常见原因是什么？

最常见的是基础镜像拉取失败，而不是 compose 文件本身有问题。这次验证里，`python:3.11-slim`、`node:20-alpine` 和 `nginx:1.27-alpine` 都卡在 `docker.io` token 获取阶段，所以证据文件里保留了真实失败日志，便于区分“配置问题”和“外部网络问题”。

### 当前最值得扩展的下一步是什么？

- 工单持久化
- 更完整的 MCP Server 暴露
- 更系统的回归数据集
- 低风险前提下的 LLM metadata extraction
