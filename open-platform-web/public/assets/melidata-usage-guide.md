# 从申请 Key 到搜索成功

从创建应用到区域搜索只有四步。先看流程，再按下方步骤完成接入；完整请求路径、参数和响应示例见 API Reference。

## 接入流程一览

| 顺序 | 环节 | 负责人 | 说明 |
| --- | --- | --- | --- |
| 01 | 开通应用与 API Key | 开通人 | 创建应用、选择所需 scope，并安全交付 API Key。 |
| 02 | 服务端写入数据 | 业务开发者 | 调用 `POST /api/v1/data/{collection}`，使用 `data:write`。 |
| 03 | CDC 自动同步 | 平台自动 | PostgreSQL → Outbox → Debezium → Kafka → 区域 Agent → Meilisearch。 |
| 04 | 通过区域 Agent 搜索 | 业务开发者 | 调用搜索端点，使用 `search:read`；写入后需等待异步同步。 |

**推荐顺序：** 开通与交付 Key → 服务端写入 → 等待 CDC 同步 → 通过区域 Agent 搜索。

## 按顺序完成接入

### 01 了解什么是 MeliData 服务

MeliData 是面向应用的统一数据与搜索服务：业务数据通过数据 API 写入，再由区域 Agent 同步到 Meilisearch，提供就近、低延迟的搜索能力。

### 02 评估与 App 的搜索需求契合度

梳理需要搜索的集合、文档字段、过滤与排序条件，以及数据更新频率。确认你的场景适合全文检索和异步同步后，再进入接入流程。

### 03 开通应用并创建 API Key

由开通人在控制台创建应用，按实际用途申请最小权限范围，并为开发、测试、生产环境分别创建 API Key。密钥只在创建时展示一次，请立即保存到密钥管理系统再交付，不要通过截图或聊天记录传递。

### 04 交给 AI 页面网址学习

将当前页面网址或 AI Agent 集成指南的网址交给你的 AI 编程助手，让它学习服务边界、鉴权要求和代码示例，再开始生成接入方案。

### 05 开发代码

让 AI 先生成代码，再由你确认请求路径、集合名称、字段映射和错误重试策略。使用服务端环境变量保存配置，不要把密钥写入前端源码。

### 06 部署时填写 API Key

部署应用时，通过平台的 Secret 或环境变量注入 API Key，例如 `MELIDATA_API_KEY`。上线前按快速开始验证完整链路：写入一条文档，等待区域同步完成，搜索能命中该文档，再接入全量数据。

## 准备开始了吗？

把首页网址交给 AI，或直接从快速开始页面复制第一段请求示例。首页也可以直接分享给 AI 编程助手作为参考资料。

- 快速开始：`/open-platform/docs/quickstart`
- AI Agent 指南：`/open-platform/docs/agent-guide`
- API Reference：`/open-platform/docs/api-reference`
- 认证规则：`/open-platform/docs/authentication`
