# UniData Producer Service

基于 FastAPI 的异地分布式搜索“生产端”服务。  
它负责把来自业务侧的结构化/半结构化数据写入 PostgreSQL，  
后续通过 Debezium + Kafka 的 CDC 链路，将这些变更实时推送到各地的 Meilisearch 节点，实现“写入集中、搜索就近”的架构。

> 可以简单理解为：UniData 把“需要被搜索的数据”标准化写入数据库，  
> 后面的 Debezium 与 Go 消费者负责把这些数据安全地送到各区域的搜索引擎。

目前数据统一通过通用文档接口 `/api/v1/data/{collection}` 写入，  
不再单独提供 testcases 专用接口。

---

## 1. 整体业务背景

在跨地域部署的场景下，如果所有搜索请求都打回同一个数据中心，会遇到：

- 网络 RTT 大，海外或异地用户搜索延迟高；
- 中心节点压力大，扩展成本高；
- 数据需要在多个区域间复制，容易出现一致性和复杂的同步逻辑。

本方案采用 **“单源写入 + CDC + 边缘搜索”** 模式：

- PostgreSQL 作为**唯一真相源（Source of Truth）**；
- Debezium 挂在 PostgreSQL 的 WAL 日志上，捕获数据变更；
- Kafka 作为消息中枢，把变更事件广播给各地消费者；
- 每个区域的 Go 消费者进程负责订阅事件并更新本地 Meilisearch 索引；
- 客户端搜索请求只打到“最近”的 Meilisearch 节点，实现高可用、低延迟。

UniData 处于这条链路的“入口”位置，主要职责是：

- 提供统一的 HTTP API，让上层业务以标准 JSON 格式写入数据；
- 对输入数据做基础校验与补全（例如确保 `id` 存在、`is_delete` 字段正确）；
- 将数据写入 PostgreSQL 的 `test_cases` 表或通用 `documents` 表，作为 CDC 的源表；
- 对外暴露应用级 JWT 认证能力，控制谁可以写入数据。

关于 Debezium + Kafka + Meilisearch 的完整部署与 CDC 流程，可参考仓库根目录下的文档：

- [docs/debezium 部署.md](file:///Users/libiao/Desktop/异地分布式部署/docs/debezium%20部署.md)

---

## 2. 业务角色和数据流

### 2.1 核心参与方

- **写入方（Producer 客户端）**  
  任何需要把数据送入搜索系统的业务服务（比如内容管理、商品中心、测试用例管理系统等），通过 HTTP 调用 UniData。

- **UniData Producer Service（本项目）**  
  使用 FastAPI 实现，负责：
  - 接收 HTTP 请求；
  - 校验并组装 JSON payload；
  - 调用业务 Service 与 Repository，将数据写入 PostgreSQL；
  - 根据 JWT 中的应用身份，将数据归属到对应 app。

- **PostgreSQL**  
  存储测试用例与通用文档数据，例如：
  - `test_cases`：测试用例；
  - `documents`：通用集合 + app 维度的文档。

- **Debezium + Kafka**  
  监听 PostgreSQL 的 WAL 日志，把表的变更转成标准 CDC 事件推入 Kafka 主题。

- **Go 消费者 + Meilisearch**  
  每个区域运行一个 Go 程序，订阅 Kafka 中的 CDC 事件：
  - `op = c/u` 时，将 `after` 数据写入/更新到 Meilisearch；
  - `op = d` 时，从 Meilisearch 删除对应文档。

### 2.2 写入与同步数据流（从业务到搜索）

1. 上游业务构造包含 `id` 字段的 JSON 对象（可以携带任意业务字段）；
2. 调用 UniData 的 `/api/v1/data/{collection}` 接口写入数据；
3. UniData：
   - 校验 JSON 格式；
   - 解析/填充业务字段（如 `is_delete`）；
   - 将完整 JSON 序列化后写入 PostgreSQL；
4. PostgreSQL 按常规方式持久化写入；
5. Debezium 监听到相关表的变更，生成 CDC 事件；
6. Kafka 分发事件到各区域；
7. Go 消费者在各区域消费事件，并据此更新 Meilisearch；
8. 各地前端/服务直接查询本地 Meilisearch，实现高性能搜索。

这条链路在业务上的好处是：

- 上游只需要会“写 JSON 到 HTTP 接口”，不需要关心同步和搜索细节；
- CDC + 消息队列把“同步逻辑”从业务代码中拆出去，大幅降低耦合；
- 使用 PostgreSQL 作为统一写入点，便于运维和审计。

---

## 3. 领域模型与表设计

### 3.1 通用 Document 模型

Pydantic 模型见：

- [app/schemas/document.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/schemas/document.py)

特点：

- 所有通用文档共享一个基础字段：
  - `id: str`：文档唯一标识；
  - 其他字段通过 `extra = "allow"` 自由扩展；
- 通过 `collection` + `app_name` 维度划分不同业务的文档空间；
- 适合管理测试用例、需求、缺陷、配置等多种类型的异构数据。

---

## 4. HTTP 接口概览

所有业务接口都挂载在 `/api/v1` 之下，由 [app/api/v1/router.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/api/v1/router.py) 统一注册：

- `/api/v1/auth`：令牌申请与审核；
- `/api/v1/data/{collection}`：通用文档接口（包括测试用例在内的所有业务数据统一通过此接口写入）。

健康检查接口：

- `GET /health`：基础探活，返回 `{ "status": "healthy" }`。

下面分块说明核心接口。

---

## 5. 通用文档接口 `/api/v1/data/{collection}`

路由定义见：

- [app/api/v1/endpoints/documents.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/api/v1/endpoints/documents.py)

该模块提供一套可复用的通用文档 CRUD 能力，用于管理任意集合（包括测试用例在内）：

### 6.1 创建/更新文档

- `POST /api/v1/data/{collection}`
- 请求体：必须包含 `id`，其他字段自由扩展；
- 示例：

```bash
curl -X POST "http://localhost:8080/api/v1/data/requirements" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <jwt>" \
  -d '{
    "id": "REQ-001",
    "title": "支付重构需求",
    "owner": "alice",
    "status": "open"
  }'
```

约束：

- `collection` 不允许包含空格；
- 实际写入会携带当前应用名 `app_name`，保证不同应用之间的文档隔离。

### 6.2 获取文档详情

- `GET /api/v1/data/{collection}/{id}`  
- 返回完整 payload 内容（Dict[str, Any]）。

### 6.3 删除文档

- `DELETE /api/v1/data/{collection}/{id}`  
- 进行软删除，更新内部标记，配合 CDC 通知搜索端。

### 6.4 列出集合文档

- `GET /api/v1/data/{collection}?limit=20&offset=0`
- 默认仅返回“当前应用”的文档；
- 如需跨应用查看，需要在服务中扩展更高权限的逻辑。

---

## 7. 认证与 Token 机制

认证模块位于：

- [app/core/auth.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/core/auth.py)
- [app/api/v1/endpoints/auth.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/api/v1/endpoints/auth.py)

### 7.1 JWT 结构

使用 HS256 对称加密，秘钥来自配置：

- `Settings.jwt_secret`（见 [config.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/core/config.py)）

载荷中包含：

- `app_name`: 应用名称；
- `scopes`: 权限列表（字符串数组或空格分隔字符串）；
- `exp`: 过期时间戳（秒）。

### 7.2 令牌签发接口

- `POST /api/v1/auth/token`
- 请求体：

```json
{
  "app_name": "my-app",
  "itcode": "alice",
  "scopes": ["write:testcases", "write:documents"],
  "ttl": 315360000
}
```

- 返回：

```json
{
  "app_name": "my-app",
  "itcode": "alice",
  "expires_at": 1893456000
}
```

说明：

- 实际生成的 JWT 会存入数据库，并通过内部的消息渠道（如工权消息）发送给 `itcode` 对应的用户；
- 审核流程由 `token_service` 负责，可通过内部系统或页面完成。

### 7.3 Token 审核与查询

- `GET /api/v1/auth/tokens/pending`：获取待审核 token 列表；
- `GET /api/v1/auth/tokens/approved`：获取已审核 token 列表；
- `POST /api/v1/auth/tokens/{token_id}/approve`：审核通过指定 token，并发送通知。

### 7.4 请求中的身份解析

业务接口（如 `/api/v1/data/...` 等）通过依赖注入获取当前应用：

- Header 要求：
  - `Authorization: Bearer <jwt>`
  - 可选 `X-App-Name: <app_name>`，用于与 JWT 内部 `app_name` 做交叉校验。

`get_current_app` 会完成：

- Bearer Token 格式校验；
- 签名验证与过期检查；
- 从 payload 中解析 `app_name` 与 `scopes`；
- 返回 `AppIdentity(app_name, scopes)` 给业务层使用。

---

## 8. 应用架构与代码结构

本项目采用典型的 FastAPI 分层结构：

- `app/main.py`  
  - 应用工厂：`create_app(settings: Optional[Settings]) -> FastAPI`；  
  - 注册路由和中间件，挂载 `/api/v1` 路由前缀；  
  - 提供 `main()` 启动函数，方便通过命令行启动服务。

- `app/api/v1`  
  - `endpoints/`: 具体业务路由（auth、testcases、documents）；  
  - `router.py`: 聚合 v1 版本下所有路由，并挂载在 `/api/v1`。

- `app/core`  
  - `config.py`: 使用 `pydantic-settings` 读取 `.env` 中的配置，如 PostgreSQL 连接串、服务端口、JWT 秘钥等；  
  - `database.py`: 管理 SQLAlchemy AsyncEngine 和 AsyncSession，提供 `get_db` 依赖和 `close_db` 生命周期钩子；  
  - `auth.py`: 实现 JWT 生成与解析。

- `app/models`  
  - ORM 模型层（测试用例、通用文档、令牌记录等）。

- `app/repositories`  
  - 直接与数据库交互的 SQL 封装，如 `testcase_repository`、`document_repository`、`token_repository`。

- `app/services`  
  - 业务逻辑层，如 `TestCaseService`、`DocumentService`、`TokenService`，负责校验、补全字段、调用 Repository。

- `tests`  
  - 使用 `pytest` + `pytest-asyncio`；  
  - `conftest.py` 提供统一的 async 测试客户端和数据库会话 fixture。

---

## 9. 环境配置与运行

### 9.1 配置项

配置通过环境变量或 `.env` 文件加载，定义在：

- [app/core/config.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/core/config.py)

主要字段：

- `pg_conn_string`：PostgreSQL 连接串，例如：

  ```text
  postgres://user:password@host:5432/unidata?sslmode=disable
  ```

- `server_port`：服务端口，形如 `:8080`，启动时会自动去掉前缀冒号；
- `meili_default_url` / `meili_default_api_key`：默认 Meilisearch 端点与密钥；
- `jwt_secret`：JWT 签名秘钥（HS256）；
- `gquan_base_url` / `gquan_app_name`：用于发送 token 审核通知的内部系统配置。

### 9.2 本地启动

推荐使用 [uv](https://github.com/astral-sh/uv) 管理 Python 环境与依赖：

```bash
cd UniData

# 1. 创建虚拟环境
uv venv

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 安装依赖
uv pip install -e .
```

启动服务：

```bash
python main.py
```

服务启动后，默认监听：

- `http://0.0.0.0:8080`

也可以使用 uvicorn 直接启动：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

### 9.3 运行测试

确保 Python 依赖已安装（推荐使用虚拟环境）：

```bash
cd UniData
pip install -e .
pip install pytest pytest-asyncio httpx
pytest
```

测试会使用 `Settings.pg_conn_string` 指向的 PostgreSQL，  
并在测试会话中自动创建相关表进行验证。

> 建议为测试准备一个单独的数据库（例如 `unidata_test`），  
> 以避免测试数据污染生产库。

---

## 10. 与 Debezium / Meilisearch 的衔接

本项目只负责将数据稳定、规范地写入 PostgreSQL。  
CDC 与搜索同步的部分在仓库其他目录中实现：

- Debezium 与 Kafka 部署文档：  
  - [docs/debezium 部署.md](file:///Users/libiao/Desktop/异地分布式部署/docs/debezium%20部署.md)
- Go 消费者与 Meilisearch 同步程序：  
  - [meilisearch-sync-service](file:///Users/libiao/Desktop/异地分布式部署/meilisearch-sync-service/main.go)
- 事件生产者样例（其他语言实现）：  
  - [producer](file:///Users/libiao/Desktop/异地分布式部署/producer/main.go)

架构上，UniData 与这些组件配合，实现：

- 从 PostgreSQL 到 Kafka 的结构化变更流；
- 从 Kafka 到各地 Meilisearch 的增量更新；
- 多区域搜索结果的一致性与高可用。

---

## 11. 后续可以扩展的方向

- 增加更多业务字段的校验与枚举约束（如类型、状态、所属项目等）；
- 为 `/api/v1/data` 增加查询/统计接口，支持按条件直接读取 PostgreSQL 中的数据；
- 细化 scopes 与权限模型，限制不同应用/角色可以操作的集合与字段；
- 引入更完整的 OpenAPI 示例与前后端协作规范。

当前版本已经可以在真实 PostgreSQL 环境下稳定运行，并与 Debezium + Meilisearch 架构顺畅对接，适合作为异地搜索架构中的“写入入口服务”与“应用级凭证中心”。
