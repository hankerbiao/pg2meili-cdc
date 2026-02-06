# 部署指南概览

本章节面向非接口使用者（如运维/部署同学），内容聚焦环境搭建与服务部署流程。

UniData 的异地分布式部署涉及多个组件的协同工作。为了方便管理与维护，我们将部署流程分为 **开源基础组件** 与 **自研业务工具** 两大部分。

建议您按照以下顺序进行部署：

## 1. 部署开源基础组件

首先搭建数据存储与消息流转的基础设施。

- **[开源组件部署](/deployment/oss)**
  - PostgreSQL (数据源)
  - Kafka + Debezium (消息中间件)
  - Meilisearch (搜索引擎)

## 2. 部署自研业务工具

在基础设施就绪后，部署业务逻辑层以串联数据流。

- **[UniData 服务部署](/deployment/unidata)**
  - 写入入口与数据生产服务 (FastAPI)
- **[自研工具部署](/deployment/internal)**
  - Debezium Connector (同步触发器)
  - Go Sync Service (异地同步服务)

---

## 开发环境部署说明（面向服务开发者）

以下内容用于服务开发与联调，帮助理解鉴权与调用方式，不面向终端用户：

- **[Token / JWT 认证说明](/deployment/token)**
- **[Token 撤销广播与缓存设计](/deployment/index#token-撤销广播与缓存设计)**

## 架构说明

- 业务方通过 HTTP 调用 UniData 写入数据。
- 数据先落在 PostgreSQL，再由 Debezium 监听变更并推送到 Kafka。
- Go 同步服务消费 Kafka 消息，将数据写入 Meilisearch。
- 查询侧通过 Search Proxy 访问 Meilisearch 获取结果。

---

## Token 撤销广播与缓存设计

本节说明多地部署下的 Token 失效同步方案，核心思路是“撤销事件广播 + 本地内存缓存 + Redis 缓存”，确保撤销能尽快生效。

### 1. 撤销广播（UniData）

- UniData 在撤销 token 时向 Kafka 发送撤销事件
- Topic：`token.revocations`
- 事件包含：`jti`、`app_name`、`reason`、`ts`

### 2. 搜索服务消费与缓存（Go 服务）

- Go 搜索服务订阅 `token.revocations`
- 收到事件后写入：
  - **本地内存缓存**（快速命中）
  - **Redis**（持久化与共享）
- `/search` 接口在验签后检查 `jti` 是否被撤销

### 3. Redis 配置（默认本机）

- `REDIS_ADDR`：默认 `127.0.0.1:6379`
- `REDIS_PASSWORD`：默认空
- `REDIS_DB`：默认 `0`
- `REVOKE_CACHE_TTL_SECONDS`：默认 `604800`（7 天）

### 4. 运行要点

- 各区域部署本地 Redis，避免跨区访问带来的延迟
- Redis 异常时应按策略降级（安全优先或可用性优先）
