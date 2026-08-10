# 异地分布式搜索架构系统

基于 CDC (Change Data Capture) 的分布式搜索同步系统，实现"单源写入 + 多区域搜索"架构。

## 架构概览

```
业务数据 → MeliData (FastAPI) → PostgreSQL (documents 表 / 动态集合)
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

- **统一写入**: 通过 FastAPI REST API 写入业务数据，支持通用文档存储
- **CDC 实时同步**: 使用 Debezium 捕获数据库变更
- **多区域搜索**: 各区域部署 Meilisearch 节点，搜索就近访问
- **软删除机制**: 通过 `is_delete` 字段标记删除状态
- **高性能搜索**: Meilisearch 提供亚毫秒级搜索延迟
- **开放平台门户**: React 文档中心、Python SDK 下载与 API Key 管理控制台

## 项目结构

```
异地分布式部署/
├── UniData/                          # MeliData FastAPI 生产者服务 (Python)
│   ├── app/
│   │   ├── main.py                   # 应用入口
│   │   ├── core/                     # 核心配置和数据库
│   │   ├── api/                      # API 路由
│   │   │   ├── v1/
│   │   │   │   ├── endpoints/        # API 端点
│   │   │   │   │   └── documents.py  # 通用文档接口
│   │   │   │   └── router.py         # v1 路由聚合
│   │   ├── models/                   # 数据模型
│   │   │   └── document.py           # Document ORM 模型
│   │   ├── services/                 # 业务逻辑层
│   │   │   └── document_service.py
│   ├── migrations/                   # 版本化数据库迁移
│   ├── tests/                        # 测试用例
│   ├── pyproject.toml
│   └── README.md
│
├── meilisearch-sync-service/         # Go 消费者服务
│   ├── internal/                     # 内部包
│   ├── main.go                       # 入口文件
│   ├── build.sh                      # 构建脚本
│   ├── go.mod                        # Go 模块定义
│   └── go.sum
│
├── open-platform-web/                 # 开放平台门户前端 (React + TypeScript)
├── python-sdk/                       # 独立 Python 客户端 SDK
├── docker/                           # 容器初始化脚本
├── Dockerfile                        # MeliData API 镜像
├── docker-compose.yml                # 核心中间件部署配置
└── README.md
```

## API 与开放平台

MeliData Docker 镜像在构建时会编译 `open-platform-web`，并将产物随镜像发布。MeliData
运行后同时提供 API、FastAPI OpenAPI 文档、Python SDK 下载和 `/open-platform/` 门户；
根路径 `/` 会跳转至开放平台。前端源码仍可在 `open-platform-web/` 独立运行开发服务器，
但生产环境不应再部署第二份静态产物。

## 快速开始

### 环境要求

- Python 3.11+
- Go 1.25+
- PostgreSQL 14+
- Meilisearch
- Apache Kafka
- Debezium Connector

### Docker 启动 MeliData（推荐）

Go Agent 保持在各区域独立部署，不包含在中心 Docker Compose 中。

```bash
cp .env.docker.example .env.docker

# 生成管理员密码摘要，将输出写入 .env.docker
docker compose --env-file .env.docker run --rm unidata \
  python scripts/hash_admin_password.py

# 摘要包含 $，在 .env.docker 中必须用单引号包住
# OPEN_PLATFORM_ADMIN_PASSWORD_HASH='$argon2id$...'

docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
DEPLOY_HOST=your-domain.com ./scripts/verify-center-deployment.sh
```

## CDC 连接器自动注册

启动后 `connect-init` 服务会向 Kafka Connect 注册 Debezium PostgreSQL CDC connector，
打通「PostgreSQL → Kafka → Meilisearch」同步链路。监控的表由 `.env.docker` 的
`CDC_TABLE_INCLUDE_LIST` 控制（默认仅公共 `public.search_outbox`；租户业务表通过
触发器原子写入 outbox，不再被 Debezium 直接监听）。`postgres-role-init` 会在每次
部署时幂等对齐 `unidata_app` 与 `unidata_cdc` 的凭证和授权，确保已有 PostgreSQL
数据卷也能使用当前 `.env.docker` 中的角色配置。

检查注册状态：

```bash
connector_name=$(awk -F= '$1 == "CDC_CONNECTOR_NAME" { name = $2 } END { print name }' .env.docker)
curl -s "http://localhost:8083/connectors/${connector_name:-pg-search-outbox-connector}/status" | jq
```

如需调整监控表或重建 connector，修改 `CDC_TABLE_INCLUDE_LIST` 后重跑：

```bash
docker compose --env-file .env.docker up -d connect-init
```

调试工具（Kafka UI 管理台）默认不启动，需要时通过 `debug` profile 单独拉起：

```bash
docker compose --env-file .env.docker --profile debug up -d kafka-ui
# 访问 http://localhost:8085
```

服务入口：

- API 文档：`http://localhost:8080/docs`
- 存活检查：`http://localhost:8080/health`
- 就绪检查：`http://localhost:8080/ready`

后端源码修改可通过 Compose Watch 同步到容器并自动重启：

```bash
docker compose --env-file .env.docker watch unidata
```

Python 依赖、SDK 或 Dockerfile 变化会触发镜像重建。生产环境必须通过 HTTPS 反向代理访问，并将 `OPEN_PLATFORM_COOKIE_SECURE` 设置为 `true`。

### 1. 安装 Python 依赖 (MeliData)

```bash
cd UniData

# 创建并激活虚拟环境 (使用 uv)
uv venv
source .venv/bin/activate

# 安装依赖
uv sync
```

### 2. 安装 Go 依赖 (Sync Service)

```bash
cd meilisearch-sync-service
go mod tidy
```

### 3. 配置环境变量

```bash
# MeliData 服务
cp UniData/.env.example UniData/.env

# Go 同步服务
cp meilisearch-sync-service/.env.example meilisearch-sync-service/.env
```

Docker 部署使用根目录的 `.env.docker.example`。所有实际 `.env` 文件均为本地配置，不应提交。

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

## API 概览

详细 API 文档请启动服务后访问 `/docs` (Swagger UI)。

### 通用文档接口

系统提供基于集合 (Collection) 的通用文档增删改查接口。

#### 创建/更新文档

```http
POST /api/v1/data/{collection_name}
Content-Type: application/json

{
  "id": "doc-001",
  "payload": {
    "title": "示例标题",
    "content": "这是一段测试内容",
    "status": "published"
  }
}
```

#### 根据 ID 获取文档

```http
GET /api/v1/data/{collection_name}/{id}
```

#### 软删除文档

```http
DELETE /api/v1/data/{collection_name}/{id}
```

## Python SDK

仓库内提供独立的 [`unidata-sdk`](python-sdk/README.md)，统一封装文档、索引、
Agent 发现与版本化搜索接口，并同时支持同步和异步 Python 客户端。

```bash
pip install ./python-sdk
```

## 部署拓扑

多区域部署中，每个区域的 Sync Service 使用独立 Kafka consumer group，组名由
`KAFKA_GROUP_PREFIX` 与 `REGION_ID` 自动生成。同一区域的多个副本共享
group 以实现故障转移，不同区域使用不同 group，以保证每个区域都收到完整数据流。
未配置 `REGION_ID` 的单区域旧部署会继续沿用 `KAFKA_GROUP_ID` 或消费者组前缀。

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

### Python 服务 (MeliData)
- **FastAPI**: Web 框架
- **SQLAlchemy + asyncpg**: 异步数据库 ORM
- **Pydantic**: 数据验证

### Go 服务 (meilisearch-sync-service)
- **franz-go**: 高性能 Kafka 客户端
- **meilisearch-go**: Meilisearch 客户端
- **Go Modules**: 依赖管理

### 文档 & 前端
- **React + TypeScript + Vite**: 独立维护的开放平台文档与管理控制台前端
- **React + Vite**: 数据与搜索调试工具
