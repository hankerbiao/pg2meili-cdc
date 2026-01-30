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

- Go 1.20+
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
| `KAFKA_GROUP_ID` | 消费者组 ID | `meilisearch-sync-service` |
| `MEILI_HOST` | Meilisearch 服务地址 | `http://10.17.154.252:7700` |
| `MEILI_API_KEY` | Meilisearch API 密钥 | 空 |

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

## 部署

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

- `app_name` 来自上游应用的 JWT 与写入 payload；
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
