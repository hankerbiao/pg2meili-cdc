# 异地分布式搜索架构系统

基于 CDC (Change Data Capture) 的分布式搜索同步系统，实现"单源写入 + 多区域搜索"架构。

## 架构概览

```
业务数据 → UniData (FastAPI) → PostgreSQL (test_cases 表)
                                    ↓
                              Debezium (CDC)
                                    ↓
                              Kafka (消息队列)
                                    ↓
                    meilisearch-sync-service (Go 消费者)
                                    ↓
                              Meilisearch (各区域节点)
```

## 核心特性

- **统一写入**: 通过 FastAPI REST API 写入业务数据
- **CDC 实时同步**: 使用 Debezium 捕获数据库变更
- **多区域搜索**: 各区域部署 Meilisearch 节点，搜索就近访问
- **软删除机制**: 通过 `is_delete` 字段标记删除状态
- **高性能搜索**: Meilisearch 提供亚毫秒级搜索延迟

## 项目结构

```
异地分布式部署/
├── UniData/                          # FastAPI 生产者服务 (Python)
│   ├── app/
│   │   ├── main.py                   # 应用入口
│   │   ├── core/                     # 核心配置和数据库
│   │   │   ├── config.py             # 配置管理
│   │   │   └── database.py           # 异步数据库连接
│   │   ├── api/                      # API 路由
│   │   │   ├── v1/
│   │   │   │   ├── endpoints/        # API 端点
│   │   │   │   │   └── testcases.py  # 测试用例接口
│   │   │   │   └── router.py         # v1 路由聚合
│   │   │   └── dependencies.py       # API 依赖项
│   │   ├── models/                   # 数据模型
│   │   │   └── testcase.py           # TestCase ORM 模型
│   │   ├── repositories/             # 数据访问层
│   │   │   └── testcase_repository.py
│   │   ├── services/                 # 业务逻辑层
│   │   │   └── testcase_service.py
│   │   └── schemas/                  # Pydantic 模式
│   │       └── testcase.py
│   ├── tests/                        # 测试用例
│   │   ├── conftest.py
│   │   └── test_testcases.py
│   ├── pyproject.toml
│   └── README.md
│
├── meilisearch-sync-service/         # Go 消费者服务
│   ├── main.go                       # 入口文件
│   └── .env.example                  # 环境变量模板
│
├── docs/                             # 部署文档
│   ├── debezium 部署.md              # CDC 部署指南
│   ├── debezium_docker-compose.yml   # Docker Compose 配置
│   ├── sql.sql                       # PostgreSQL 表结构
│   └── init_fastapi.md               # FastAPI 模板参考
│
├── .env                              # 环境变量
├── .env.example                      # 环境变量模板
├── go.mod
└── go.sum
```

## 快速开始

### 环境要求

- Python 3.10+
- Go 1.25+
- PostgreSQL 14+
- Meilisearch
- Apache Kafka
- Debezium Connector

### 1. 安装 Python 依赖

```bash
cd UniData
uv sync
```

### 2. 安装 Go 依赖

```bash
cd meilisearch-sync-service
go mod tidy
```

### 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置
vim .env
```

### 4. 启动服务

**启动 FastAPI 服务:**

```bash
cd UniData
uv run python main.py
# 或使用 uvicorn
uvicorn app.main:create_app --host 0.0.0.0 --port 8000 --reload
```

**启动 Go 消费者:**

```bash
cd meilisearch-sync-service
go run main.go
```

## 配置说明

### FastAPI 配置 (UniData/.env)

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PG_CONN_STRING` | PostgreSQL 连接字符串 | - |
| `SERVER_PORT` | 服务端口 | 8000 |
| `MEILI_DEFAULT_URL` | Meilisearch 地址 | - |
| `MEILI_DEFAULT_API_KEY` | Meilisearch API Key | - |

### Go 消费者配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `KAFKA_BROKERS` | Kafka 集群地址 | - |
| `KAFKA_TOPIC` | Debezium 主题 | - |
| `KAFKA_GROUP_ID` | 消费者组 ID | - |
| `MEILI_HOST` | Meilisearch 地址 | - |
| `MEILI_API_KEY` | Meilisearch API Key | - |
| `MEILI_INDEX` | 索引名称 | - |

## API 文档

### 测试用例接口

#### 创建/更新测试用例

```http
POST /api/v1/testcases
Content-Type: application/json

{
  "id": "test-001",
  "payload": {
    "name": "测试用例名称",
    "description": "测试描述",
    "status": "active"
  }
}
```

#### 根据 ID 更新

```http
PUT /api/v1/testcases/{id}
Content-Type: application/json

{
  "payload": {
    "name": "更新后的名称"
  }
}
```

#### 软删除

```http
DELETE /api/v1/testcases/{id}
```

#### 获取 Meilisearch 配置

```http
GET /api/v1/testcases/meilisearch/endpoint
```

#### 健康检查

```http
GET /health
```

## 数据模型

### TestCase 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String | 主键 |
| payload | JSONB | 业务数据 |
| updated_at | DateTime | 更新时间 |

### payload 结构示例

```json
{
  "name": "测试用例名称",
  "description": "测试描述",
  "is_delete": false
}
```

## CDC 数据流

### Debezium 消息格式

```json
{
  "before": null,
  "after": {
    "id": "test-001",
    "payload": {...},
    "updated_at": "2024-01-01T00:00:00Z"
  },
  "op": "c"
}
```

### 操作类型 (op)

| 值 | 说明 | Meilisearch 操作 |
|----|------|------------------|
| `c` | 创建 | 添加文档 |
| `r` | 读取 | 添加文档 |
| `u` | 更新 | 添加文档 |
| `d` | 删除 | 删除文档 |

## 部署拓扑

```
                        ┌─────────────────┐
                        │   PostgreSQL    │
                        │  (主数据中心)   │
                        └────────┬────────┘
                                 │
                                 │ Debezium CDC
                                 ▼
                        ┌─────────────────┐
                        │  Kafka 集群     │
                        │ (消息总线)      │
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │  Meilisearch    │ │  Meilisearch    │ │  Meilisearch    │
    │  (区域 A)       │ │  (区域 B)       │ │  (区域 C)       │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
```

## 技术栈

### Python 服务 (UniData)

- **FastAPI**: Web 框架
- **uvicorn**: ASGI 服务器
- **SQLAlchemy + asyncpg**: 异步数据库 ORM
- **Pydantic**: 数据验证
- **pytest**: 测试框架

### Go 服务 (meilisearch-sync-service)

- **franz-go**: Kafka 客户端
- **meilisearch-go**: Meilisearch 客户端
- **pgx**: PostgreSQL 驱动

## 开发指南

### 添加新的 API 端点

1. 在 `app/api/v1/endpoints/` 创建新的端点文件
2. 在 `app/api/v1/router.py` 注册路由
3. 创建对应的 Service 和 Repository 层

### 添加新的数据模型

1. 在 `app/models/` 创建 ORM 模型
2. 在 `app/schemas/` 创建 Pydantic 模式
3. 在 `app/repositories/` 创建数据访问层
4. 在 `app/services/` 创建业务逻辑层

## 测试

```bash
# 运行 Python 测试
cd UniData
uv run pytest tests/

# 运行 Go 测试
cd meilisearch-sync-service
go test ./...
```

## 相关文档

- [Debezium 部署指南](docs/debezium%20%E9%83%A8%E7%BD%B2.md)
- [PostgreSQL 表结构](docs/sql.sql)
- [Docker Compose 配置](docs/debezium_docker-compose.yml)