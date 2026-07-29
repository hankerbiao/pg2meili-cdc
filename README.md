# 异地分布式搜索架构系统

基于 CDC (Change Data Capture) 的分布式搜索同步系统，实现"单源写入 + 多区域搜索"架构。

## 架构概览

```
业务数据 → UniData (FastAPI) → PostgreSQL (documents 表 / 动态集合)
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
- **现代化文档**: 集成 VitePress 文档中心

## 项目结构

```
异地分布式部署/
├── UniData/                          # FastAPI 生产者服务 (Python)
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
│   │   └── templates/                # HTML 模板 (Token 申请等)
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
├── docs/                             # VitePress 文档中心
│   ├── .vitepress/
│   ├── deployment/                   # 部署指南
│   ├── guide/                        # 使用指南
│   └── index.md
│
├── frontend/                         # 前端演示应用 (React)
├── libs/                             # 静态资源库 (Layui 等)
├── docker-compose.yml                # 核心中间件部署配置
└── README.md
```

## 文档中心 (VitePress)

本项目使用 VitePress 构建了现代化的文档中心，包含：
- **详细 API 接口说明**: 包含通用文档 CRUD、Token 申请等完整接口定义
- **环境部署指南**: PostgreSQL, Debezium, Kafka, Meilisearch 等组件的详细部署方案
- **开发使用手册**: Token 申请流程、SDK 使用示例等

详细的接口文档和部署说明请参考 VitePress 文档。

### 部署与使用

1. **环境准备**
   确保本地已安装 Node.js (推荐 v18+)。

2. **安装依赖**
   ```bash
   # 在项目根目录下执行
   npm install
   ```

3. **启动本地预览**
   ```bash
   npm run docs:dev
   ```
   启动后访问 `http://localhost:5173` 即可查看完整文档。

4. **构建静态站点**
   ```bash
   npm run docs:build
   ```
   构建产物位于 `docs/.vitepress/dist`，可部署至 Nginx 或 GitHub Pages。

## 快速开始

### 环境要求

- Python 3.11+
- Go 1.25+
- PostgreSQL 14+
- Meilisearch
- Apache Kafka
- Debezium Connector

### 1. 安装 Python 依赖 (UniData)

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
- **SQLAlchemy + asyncpg**: 异步数据库 ORM
- **Pydantic**: 数据验证

### Go 服务 (meilisearch-sync-service)
- **franz-go**: 高性能 Kafka 客户端
- **meilisearch-go**: Meilisearch 客户端
- **Go Modules**: 依赖管理

### 文档 & 前端
- **VitePress**: 静态文档站点
- **React + Vite**: 演示前端
