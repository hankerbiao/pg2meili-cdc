# UniData Producer Service

基于 FastAPI 的异地分布式搜索“生产端”服务。  
它负责把来自业务侧的结构化/半结构化数据写入 PostgreSQL 中的 `test_cases` 表，  
后续通过 Debezium + Kafka 的 CDC 链路，将这些变更实时推送到各地的 Meilisearch 节点，实现“写入集中、搜索就近”的架构。

> 可以简单理解为：UniData 把“需要被搜索的数据”标准化写入数据库，  
> 后面的 Debezium 与 Go 消费者负责把这些数据安全地送到各区域的搜索引擎。

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
- 将数据写入 PostgreSQL 的 `test_cases` 表，作为 CDC 的源表。

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
  - 调用业务 Service 与 Repository，将数据写入 PostgreSQL。

- **PostgreSQL**  
  存储表 `test_cases`，字段包括：
  - `id`: 主键标识；
  - `payload`: 文本形式存储完整的 JSON 字符串；
  - `updated_at`: 更新时间戳，用于审计与排序。

- **Debezium + Kafka**  
  监听 PostgreSQL 的 WAL 日志，把 `test_cases` 表的变更转成标准 CDC 事件推入 Kafka 主题。

- **Go 消费者 + Meilisearch**  
  每个区域运行一个 Go 程序，订阅 Kafka 中的 CDC 事件：
  - `op = c/u` 时，将 `after` 数据写入/更新到 Meilisearch；
  - `op = d` 时，从 Meilisearch 删除对应文档。

### 2.2 写入与同步数据流（从业务到搜索）

1. 上游业务构造包含 `id` 字段的 JSON 对象（可以携带任意业务字段）；
2. 调用 UniData 的 `/api/v1/testcases` 接口写入数据；
3. UniData：
   - 校验 JSON 格式；
   - 解析/填充业务字段（如 `is_delete`）；
   - 将完整 JSON 序列化后写入 `test_cases.payload`；
4. PostgreSQL 按常规方式持久化写入；
5. Debezium 监听到 `test_cases` 表的变更，生成 CDC 事件；
6. Kafka 分发事件到各区域；
7. Go 消费者在各区域消费事件，并据此更新 Meilisearch；
8. 各地前端/服务直接查询本地 Meilisearch，实现高性能搜索。

这条链路在业务上的好处是：

- 上游只需要会“写 JSON 到 HTTP 接口”，不需要关心同步和搜索细节；
- CDC + 消息队列把“同步逻辑”从业务代码中拆出去，大幅降低耦合；
- 使用 PostgreSQL 作为统一写入点，便于运维和审计。

---

## 3. 领域模型与表设计

### 3.1 TestCase 模型

Python 模型定义见：

- [app/models/testcase.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/models/testcase.py#L1-L19)

核心字段：

- `id: str`  
  主键，表示该条数据的唯一标识。对上游业务而言可以是业务 ID，也可以是搜索文档 ID。

- `payload: Text`  
  原始 JSON 字符串，包含业务侧提交的完整数据，例如：
  ```json
  {
    "id": "case-123",
    "title": "支付接口回归测试",
    "type": "regression",
    "is_delete": false,
    "project": "payment",
    "owner": "qa-team"
  }
  ```

- `updated_at: datetime`  
  更新时间，配合 CDC 和搜索端，可以实现增量同步和排序。

### 3.2 Repository 层：PostgreSQL 写入方式

具体 SQL 在：

- [app/repositories/testcase_repository.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/repositories/testcase_repository.py#L10-L61)

特点：

- 写入使用 `INSERT ... ON CONFLICT (id) DO UPDATE`，实现幂等的“写入即更新”语义；
- 软删除使用 `jsonb_set` 将 `payload` 中的 `is_delete` 字段置为 `true`；
- 适配 PostgreSQL 的 JSONB 能力，方便后续 CDC 及搜索端按字段过滤。

---

## 4. HTTP 接口设计

当前版本提供两类与 `test_cases` 表相关的接口，均挂在 `/api/v1/testcases` 之下。  
路由定义见：

- [app/api/v1/endpoints/testcases.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/api/v1/endpoints/testcases.py#L1-L85)

### 4.1 创建/更新 Test Case

- **URL**: `POST /api/v1/testcases`
- **请求体**: 任意合法 JSON，但必须包含字段 `id`。
- **返回**: 标准响应包：
  ```json
  {
    "status": "success",
    "id": "your-id"
  }
  ```

业务规则：

- 请求体必须是合法 JSON，否则返回 `400 Invalid JSON format`；
- `id` 为必填字段，缺失或为空则返回 `400 Missing 'id' field`；
- 如果请求体中未显式传 `is_delete`，服务会自动补充为 `false`；
- 每次写入都视为“新版本”，通过 ON CONFLICT 语义更新 `payload` 与 `updated_at`。

一个典型请求示例：

```bash
curl -X POST "http://localhost:8080/api/v1/testcases" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "case-001",
    "title": "登录功能测试",
    "module": "auth",
    "priority": "P1"
  }'
```

### 4.2 软删除 Test Case

- **URL**: `DELETE /api/v1/testcases/{id}`
- **路径参数**:
  - `id`: 要删除的 Test Case 标识
- **返回**:
  ```json
  {
    "status": "success",
    "id": "case-001"
  }
  ```

业务规则：

- 不直接删除行，而是更新 `payload` 中的 `is_delete` 字段为 `true`；
- 删除操作同样会被 Debezium 观察到，并通过 CDC 事件告诉下游“该文档应该被从索引中移除或标记为已删除”；
- 如果 `id` 为空，返回 `400 Missing 'id' param`。

对应 CDC 流程中，Go 消费者会根据 `is_delete` 或操作类型，在 Meilisearch 侧删除该文档。

### 4.3 健康检查

- **URL**: `GET /health`
- **返回**:
  ```json
  {
    "status": "healthy"
  }
  ```

用于基础探活，可以配置在负载均衡或 K8s liveness/readiness 探针中。

---

## 5. 应用架构与代码结构

本项目采用典型的 FastAPI 分层结构：

- `app/main.py`  
  - 应用工厂：`create_app(settings: Optional[Settings]) -> FastAPI`  
  - 创建 FastAPI 实例、注册路由和中间件、配置生命周期管理；
  - 提供 `main()` 启动函数，方便通过脚本或命令行启动服务。

- `app/api/v1`  
  - `endpoints/`: 具体业务路由，例如 `testcases.py`；
  - `router.py`: 聚合 v1 版本下所有路由，并挂载在 `/api/v1`。

- `app/core`  
  - `config.py`: 使用 `pydantic-settings` 读取 `.env` 中的配置，如 PostgreSQL 连接串、服务端口等；
  - `database.py`: 管理 SQLAlchemy AsyncEngine 和 AsyncSession，提供 `get_db` 依赖和 `close_db` 生命周期钩子。

- `app/models`  
  - ORM 模型层（当前只有 `TestCase`）。

- `app/repositories`  
  - 直接与数据库交互的 SQL 封装，例如 `testcase_repository`。

- `app/services`  
  - 业务逻辑层，例如 `TestCaseService`，负责校验、补全字段、调用 Repository。

- `tests`  
  - 使用 `pytest` + `pytest-asyncio`；
  - `conftest.py` 提供统一的 async 测试客户端和数据库会话 fixture；
  - `test_testcases.py` 校验路由注册和健康检查。

这种分层方式的好处：

- 路由层只关心“接口协议”，业务逻辑集中在 Service；
- Service 与 Repository 解耦，方便重构和单元测试；
- Database 相关细节集中在 core/database，有利于未来扩展读写分离或多数据源。

---

## 6. 环境配置与运行

### 6.1 配置项

配置通过环境变量或 `.env` 文件加载，定义在：

- [app/core/config.py](file:///Users/libiao/Desktop/异地分布式部署/UniData/app/core/config.py#L7-L20)

主要字段：

- `pg_conn_string`  
  PostgreSQL 连接串，例如：
  ```text
  postgres://user:password@host:5432/unidata?sslmode=disable
  ```

- `server_port`  
  服务端口，形如 `:8080`，启动时会自动去掉前缀冒号。

### 6.2 本地启动

在仓库根目录：

```bash
cd UniData
python main.py
```

服务启动后，默认监听：

- `http://0.0.0.0:8080`

也可以使用 uvicorn 直接启动：

```bash
cd UniData
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

### 6.3 运行测试

确保 Python 依赖已安装（推荐使用虚拟环境）：

```bash
cd UniData
pip install -e .
pip install pytest pytest-asyncio httpx
pytest
```

测试会使用 `Settings.pg_conn_string` 指向的 PostgreSQL，  
并在测试会话中自动创建 `test_cases` 表进行验证。

> 建议为测试准备一个单独的数据库（例如 `unidata_test`），  
> 以避免测试数据污染生产库。

---

## 7. 与 Debezium / Meilisearch 的衔接

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

## 8. 后续可以扩展的方向

- 增加更多业务字段的校验与枚举约束（如类型、状态、所属项目等）；
- 为 `/api/v1/testcases` 增加查询接口，支持按条件直接读取 PostgreSQL 中的数据；
- 加入鉴权机制，限制谁可以写入或删除 Test Case；
- 引入 OpenAPI 文档示例与前后端协作规范。

当前版本已经可以在真实 PostgreSQL 环境下稳定运行，并与 Debezium + Meilisearch 架构顺畅对接，适合作为异地搜索架构中的“写入入口服务”。
