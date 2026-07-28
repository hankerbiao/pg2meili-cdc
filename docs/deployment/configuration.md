# 配置介绍

本章节详细说明各组件的配置项，包括环境变量和配置文件。

## 1. UniData 服务配置

UniData 配置主要通过环境变量或 `.env` 文件加载。核心定义位于 `app/core/config.py`。

| 变量名 | 必填 | 说明 | 默认值/示例 |
| :--- | :--- | :--- | :--- |
| `PG_CONN_STRING` | 是 | PostgreSQL 连接字符串 | `postgres://user:pass@host:5432/unidata` |
| `SERVER_PORT` | 否 | 服务监听端口 | `:8080` |
| `JWT_SECRET` | 是 | JWT 签名秘钥 (HS256) | `your-secret-key-change-it` |
| `CORS_ALLOW_ORIGINS` | 否 | 允许的跨域来源，多个值用逗号分隔 | `*` |
| `KAFKA_BOOTSTRAP_SERVERS` | 否 | Kafka Broker 地址，多个值用逗号分隔 | `kafka:9092` |
| `KAFKA_TOKEN_REVOKE_TOPIC` | 否 | Token 撤销广播 Topic | `token.revocations` |

## 2. Sync Service (Go Agent) 配置

Go 同步服务通过环境变量读取配置，支持从 `.env` 文件加载（启动时自动读取）。

### 2.1 基础配置

| 变量名 | 说明 | 示例 |
| :--- | :--- | :--- |
| `UNIDATA_URL` | **[必需]** UniData 中心服务地址，用于注册和心跳 | `http://10.32.129.188:8080` |
| `HTTP_ADDR` | 服务监听地址 | `:8091` |
| `KAFKA_BROKERS` | Kafka 连接地址，多个值用逗号分隔 | `kafka:9092` |
| `KAFKA_TOPIC` | Debezium 数据 Topic，多个值用逗号分隔 | `search_sync.public.uni_documents` |
| `MEILI_HOST` | 本地 Meilisearch 地址 | `http://localhost:7700` |
| `MEILI_API_KEY` | 本地 Meilisearch 密钥 | `my_master_key` |
| `KAFKA_TOKEN_REVOKE_TOPIC` | 撤销广播 Topic | `token.revocations` |

### 2.2 代理注册配置 (Agent Meta)

用于向中心服务汇报节点信息。

| 变量名 | 说明 |
| :--- | :--- |
| `AGENT_IP` | 代理对外 IP（不填则自动探测本机 IPv4） |
| `AGENT_PORT` | 代理对外端口（不填则使用 `HTTP_ADDR` 解析端口） |
| `AGENT_NAME` | 节点名称/主机名（不填则使用系统 hostname） |
| `AGENT_VERSION` | 代理版本号 |
| `AGENT_META` | 扩展元信息（JSON 字符串），如 `{"region":"tj"}` |

### 2.3 Redis 缓存配置 (Token 撤销)

用于多地部署下的 Token 撤销同步。

| 变量名 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `REDIS_ADDR` | Redis 地址 | `127.0.0.1:6379` |
| `REDIS_PASSWORD` | Redis 密码 | (空) |
| `REDIS_DB` | Redis 数据库索引 | `0` |
| `REVOKE_CACHE_TTL_SECONDS` | 撤销记录缓存时间（设为 0 表示永久保存） | `0` (永久) |

## 3. Debezium Connector 配置

注册 Connector 时的 JSON 配置参数说明。

| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `connector.class` | 连接器类名 | `io.debezium.connector.postgresql.PostgresConnector` |
| `database.hostname` | PG 数据库主机 | `host.docker.internal` |
| `topic.prefix` | Kafka Topic 前缀 | `search_sync` |
| `table.include.list` | 监听的表名单 | `public.payload` |
| `column.include.list` | 监听的列名单 | `public.payload.(id,title...)` |
| `plugin.name` | 逻辑解码插件 | `pgoutput` (推荐) |

### 3.1 注册 Connector 示例脚本

```bash
curl -i -X POST -H "Accept:application/json" -H "Content-Type:application/json" \
localhost:8083/connectors/ -d '{
  "name": "meili-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "host.docker.internal",
    "database.port": "5432",
    "database.user": "postgres",
    "database.password": "kk123123",
    "database.dbname": "postgres",
    "topic.prefix": "uni_documents",
    "table.include.list": "public.uni_documents",
    "plugin.name": "pgoutput",
    "column.include.list": "public.uni_documents.(id|collection|app_name|payload|is_delete)"
  }
}'
```
