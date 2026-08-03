# Meilisearch Sync Service

一个基于 Go 的实时数据同步服务，从 Kafka 消费 Debezium CDC 消息并同步到 Meilisearch 搜索引擎。

## 功能特性

- 实时消费 Kafka 中的 Debezium 变更数据捕获 (CDC) 消息
- 支持多种数据库操作类型：
  - `c` (create) - 插入
  - `u` (update) - 更新
  - `d` (delete) - 删除
  - `r` (snapshot) - 快照
- 支持多 Topic 自动路由到不同的 Meilisearch 索引
- 支持基于文档字段的动态索引命名
- 优雅退出机制

## 快速开始

### 环境要求

- Go 1.25.4+
- Kafka 集群
- Meilisearch 实例

### 配置

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

#### 配置项说明

| 环境变量 | 描述 | 默认值 |
|---------|------|--------|
| `KAFKA_BROKERS` | Kafka 集群地址 | `10.17.154.252:9092` |
| `KAFKA_TOPIC` | 订阅的 Topic 列表（逗号分隔） | `test_case.public.test_cases` |
| `REGION_ID` | 部署区域标识；多区域部署必填，不同区域必须不同 | 空 |
| `KAFKA_GROUP_PREFIX` | 消费者组前缀 | `meilisearch-sync-service` |
| `KAFKA_GROUP_ID` | 未配置 `REGION_ID` 时兼容旧部署使用的消费者组 | 空 |
| `MEILI_HOST` | Meilisearch 服务地址 | `http://10.17.154.252:7700` |
| `MEILI_API_KEY` | Meilisearch API 密钥 | 空 |
| `AGENT_PUBLIC_URL` | 外部服务访问 Agent 的稳定地址 | 自动使用 Agent IP 和端口 |
| `AGENT_REGISTRATION_TOKEN` | 向 UniData 注册时使用的共享凭证 | 无 |

最终消费者组由程序生成：

```text
{KAFKA_GROUP_PREFIX}-{REGION_ID}
```

例如，北京区域的两个副本都配置 `REGION_ID=beijing`，共同使用
`meilisearch-sync-service-beijing`；上海区域配置 `REGION_ID=shanghai`，使用
`meilisearch-sync-service-shanghai`。Kafka 会在同一区域的副本之间分配分区，
同时向不同区域的 group 分别投递完整消息流。

配置 `REGION_ID` 后，`KAFKA_GROUP_ID` 被区域化配置取代；若它仍然存在，值必须
与程序派生的 group 完全一致。未配置 `REGION_ID` 时，服务继续使用
`KAFKA_GROUP_ID`，未设置该变量则使用 `KAFKA_GROUP_PREFIX`，以保持旧部署 offset。
新 group 在没有已提交 offset 时会从 Kafka 当前仍保留的最早消息开始消费。

### 运行

```bash
# 构建
go build -o meilisearch-sync-service .

# 运行
./meilisearch-sync-service
```

或者直接运行源码：

```bash
go run main.go
```

## API 接口

服务提供了一个 HTTP 代理接口，用于安全地访问 Meilisearch。该接口根据开放平台 API Key 对应的应用标识和请求中的集合名称路由到正确索引。

新后端服务推荐使用：

```http
POST /api/v1/collections/{collection}/search
```

该接口返回统一的 `{data, meta, error}` JSON 响应，并通过 `X-Request-ID`
关联调用链。原有 `POST /search?collection={collection}` 保持兼容。

### 搜索代理接口

**Endpoint:** `POST /search`

**端口:** 默认为 `8091` (可通过 `HTTP_ADDR` 环境变量配置)

**请求头 (Headers):**

| Header | 说明 | 示例 |
|--------|------|------|
| `Authorization` | **必填**。格式为 `Bearer <API Key>`，且 Key 需要 `search:read`。 | `Bearer ud_live_ak_...` |
| `Content-Type` | **必填**。 | `application/json` |

**查询参数 (Query Parameters):**

| 参数名 | 说明 | 示例 |
|--------|------|------|
| `collection` | **必填**。数据集合名称。将与 API Key 所属应用组合成索引名 `{AppName}_{collection}`。 | `cases` |

**请求体 (Body):**

标准的 Meilisearch 搜索请求体。

```json
{
  "q": "搜索关键词",
  "limit": 10,
  "offset": 0,
  "filter": ["status = 'active'"]
}
```

**响应:**

返回 Meilisearch 的标准搜索结果。

**工作原理:**

1. 解析 `Authorization` 头中的 API Key，从区域 Redis 注册表读取应用、状态与 scopes。
2. 获取 `collection` 参数 (例如 `cases`)。
3. 拼接目标索引名称: `my_app_cases`。
4. 将请求转发至 Meilisearch: `POST /indexes/my_app_cases/search`。

## 部署

### 多区域消费者组

多区域部署中，每个区域必须使用唯一的 `REGION_ID`，同一区域内的所有副本必须复用相同值：

```text
Kafka topic
  |- group=meilisearch-sync-service-beijing
  |    |- agent-bj-1
  |    `- agent-bj-2
  `- group=meilisearch-sync-service-shanghai
       |- agent-sh-1
       `- agent-sh-2
```

不要让不同区域共享一个 group，否则 Kafka 会把分区分摊给各区域，导致每个
Meilisearch 只持有部分数据。区域内副本数超过 topic 分区数时，多出的副本会
处于待命状态，这是 Kafka consumer group 的正常行为。

从历史上被多个区域共享的 group 迁移时，各区域索引通常已经缺少一部分数据。
创建区域化 group 只能保证后续消息完整投递，不能恢复已经超过 Kafka 保留期的
历史记录。上线前应清空或新建区域索引，通过 Debezium snapshot 或全量回灌重建，
再核对 PostgreSQL 与各区域 Meilisearch 的文档数量后切换搜索流量。

```bash
# 构建二进制文件
CGO_ENABLED=0 go build -a -ldflags "-s -w" -o meilisearch-sync-service main.go

# 后台运行
nohup ./meilisearch-sync-service > app.log 2>&1 &
```

## 索引命名规则

当前索引名由文档中的应用名和集合名共同决定：

```text
{app_name}_{collection}
```

- `app_name` 来自开放平台 API Key 关联的应用身份与写入 payload；
- `collection` 来自上游写入 UniData 时指定的集合名称。

## 工作流程

```
Kafka (Debezium) --> 消费消息 --> 解析 Payload --> 操作判断 --> Meilisearch
                           |
                           +-- c/r/u --> AddDocuments (Upsert)
                           +-- d     --> DeleteDocument
```

## 消息格式

服务期望接收符合 Debezium 格式的 JSON 消息：

```json
{
  "payload": {
    "before": null,
    "after": {
      "id": 1,
      "name": "test case name",
      "status": "active"
    },
    "op": "c"
  }
}
```

对于删除操作：

```json
{
  "payload": {
    "before": {
      "id": 1
    },
    "after": null,
    "op": "d"
  }
}
```

## License

MIT
