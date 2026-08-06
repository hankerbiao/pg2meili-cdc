# 租户物理隔离实现文档（app_id 维度）

> 本文档描述当前仓库已落地的「按开放平台应用租户做 PostgreSQL 与 Meilisearch 物理隔离」
> 实现，覆盖设计约束、关键代码位置、部署方式、迁移步骤、测试范围与剩余运维工作。
> 适用提交范围：2026-08-05 起合并的租户隔离相关改动。

---

## 1. 背景与目标

原实现把全部应用文档写入 `public.uni_documents`，Meilisearch 索引名由
`app_name + collection` 推导。该方案存在三个主要问题：

- 应用重命名会让索引名漂移，历史索引与实际索引对不上。
- 所有应用共享同一张业务表，跨租户访问只能依赖应用层过滤，缺少数据库级兜底。
- CDC 直接监听业务表，任何一次误删/误改都可能把错误数据同步到错误的索引。

本次实现将 `OpenPlatformApp` 作为租户边界，`app_id` 作为不可变租户标识：

- PostgreSQL：每个应用一个独立 schema，表级启用 RLS，事务内设置租户上下文。
- CDC：租户表通过事务触发器把变更写入公共 `public.search_outbox`，Debezium 只监听 outbox。
- Meilisearch：每个 `(app_id, collection)` 使用独立 index，索引 UID 由 `app_id` 稳定推导。
- 搜索代理：API Key 解析出的 `app_id` 决定可访问的 index，不信任客户端传入的索引名。
- 生命周期：创建应用时自动初始化租户资源；删除应用时冻结鉴权、撤销 Key、删除索引、回收 schema。

`app_name` 仅作为展示和兼容字段，不再参与安全边界。

---

## 2. 总体架构

```text
API Key / 控制台
       │
       ▼
UniData (FastAPI)
  ├─ 控制面：open_platform_apps / api_keys / collection_settings / outbox / 审计
  └─ 租户面：tenant_<hash(app_id)>.uni_documents（RLS + CDC trigger）
       │
       ▼ 同事务写入
public.search_outbox（公共传输表，非业务主存储）
       │
       ▼ Debezium（pgoutput，仅 public.search_outbox）
Kafka topic: pg.public.search_outbox
       │
       ▼
meilisearch-sync-service (Go)
  ├─ outbox 事件解析：app_id + collection + document_id + operation
  ├─ 命令处理：update_settings / delete_index，校验 index_uid 与租户路由一致
  └─ 搜索代理：按 API Key 的 app_id 路由到 t_<hash(app_id)>__<collection>
       │
       ▼
Meilisearch（每租户每集合独立 index）
```

公共 outbox 是 CDC 传输层，不是业务数据主存储；它会短暂承载多个租户的变更事件，
因此通过数据库权限、网络隔离和审计保护，业务 API 不直接读写它。

---

## 3. 租户身份与命名

统一命名逻辑位于 `UniData/app/core/tenant.py`，Python 与 Go 保持相同算法。

| 资源 | 规则 | 示例 |
| --- | --- | --- |
| PostgreSQL schema | `tenant_` + `sha256(app_id)[:32]` | `tenant_90f374a04c60...` |
| Meilisearch index | `t_` + `sha256(app_id)[:16]` + `__` + collection | `t_9b31c0a8__orders` |

约束：

- 只使用 `app_id` 推导，应用改名不改变 schema/index。
- collection 必须匹配 `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`，拒绝 SQL 标识符注入与路径穿越。
- schema 名在进入 DDL 前再次校验，只允许 `tenant_` 前缀加十六进制字符。
- 同一 `app_id` 始终生成相同名称；不同 `app_id` 即使内容相同也生成不同名称。

Go 侧实现：

- `model.IndexUID(appID, collection)`：`meilisearch-sync-service/internal/model/model.go`
- 搜索代理按 `identity.AppID` 路由：`meilisearch-sync-service/internal/handler/search_v1.go`
- 同步服务按事件中的 `app_id` 路由：`meilisearch-sync-service/internal/service/sync.go`

---

## 4. PostgreSQL 租户模型

### 4.1 公共控制面

以下表保留在 `public` schema，属于平台控制面，不按租户拆分：

- `open_platform_apps`
- `api_keys`
- `collection_settings`
- `open_platform_audit_logs`
- `open_platform_outbox`
- `search_outbox`（公共 CDC 传输表）
- `unidata_schema_migrations`

### 4.2 租户 schema

每个应用创建独立 schema，例如 `tenant_90f374a0...`，其中包含：

```text
<tenant_schema>.uni_documents
```

表结构（与旧 `public.uni_documents` 对齐）：

```text
row_id       UUID PRIMARY KEY DEFAULT gen_random_uuid()
id           VARCHAR NOT NULL
app_id       VARCHAR NOT NULL
collection   VARCHAR NOT NULL
app_name     VARCHAR NOT NULL
payload      JSONB
is_delete    BOOLEAN NOT NULL DEFAULT FALSE
created_at   TIMESTAMP NOT NULL DEFAULT NOW()
updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
```

约束与索引：

- `UNIQUE (app_id, collection, id)`
- `FOREIGN KEY (app_id) REFERENCES public.open_platform_apps(id) ON DELETE RESTRICT`
- `CHECK (app_id = '<当前租户 app_id>')`，防止业务代码写入错误租户
- `(app_id, collection)` 查询索引
- `(collection, id)` 查询索引
- `REPLICA IDENTITY FULL`，保证删除事件包含完整路由字段

### 4.3 RLS

租户表启用并强制 RLS：

```sql
ALTER TABLE <schema>.uni_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE <schema>.uni_documents FORCE ROW LEVEL SECURITY;
```

策略：

```sql
CREATE POLICY tenant_isolation ON <schema>.uni_documents
USING (app_id = current_setting('app.tenant_id', true))
WITH CHECK (app_id = current_setting('app.tenant_id', true));
```

访问原则：

- API Key 鉴权只查公共控制面。
- 文档 CRUD、集合统计、索引管理必须走租户上下文。
- 管理员访问租户数据也必须显式指定目标 `app_id`。
- 业务数据库角色必须是普通角色（非超级用户），否则 RLS 会被 PostgreSQL 绕过。

### 4.4 事务上下文

`UniData/app/core/tenant.py` 的 `set_tenant_context()` 在每个租户操作前执行：

```sql
SELECT set_config('app.tenant_id', :app_id, true);
SET LOCAL search_path TO "<tenant_schema>", public;
```

两条语句都是事务级设置，连接归还连接池后不会残留上一个租户的上下文。
ORM 语句通过 `schema_translate_map={None: tenant_schema}` 绑定到当前 schema，
不把 `SET search_path` 当作长期连接状态。

仓储层入口位于 `UniData/app/repositories/document_repository.py`：

- upsert / 查询 / 软删除 / 集合聚合都会先 `ensure_tenant()` 再 `set_tenant_context()`。
- 公共控制面查询不经过该入口，不会被错误路由到租户 schema。

---

## 5. CDC Outbox

### 5.1 公共表

`public.search_outbox` 由 `ensure_search_outbox()` 幂等创建/修复：

```text
event_id       UUID PRIMARY KEY DEFAULT gen_random_uuid()
app_id         VARCHAR NOT NULL
collection     VARCHAR NOT NULL
document_id    VARCHAR NOT NULL
operation      VARCHAR NOT NULL CHECK (operation IN ('upsert', 'delete'))
document       JSONB NULL
event_version  BIGINT NOT NULL DEFAULT nextval('public.search_outbox_event_version_seq')
created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

字段语义：

- `operation=upsert`：document 保存 Meilisearch 所需业务文档（payload + id）。
- `operation=delete`：document 为 NULL，只携带路由字段。
- `app_id` / `collection` / `document_id` 是强制路由字段，缺失时触发器直接报错。
- `event_id` 用于排障和后续幂等去重。
- `event_version` 来自数据库序列，保证同一租户内事件有序。

兼容旧表：如果库里已存在旧版 `search_outbox`（没有默认值、`event_version` 为
INTEGER），`ensure_search_outbox()` 会补齐默认值、把 `event_version` 升级为 BIGINT、
补 `operation` CHECK，并让触发器显式生成 `event_id` / `event_version`，不依赖表默认值。

### 5.2 触发器语义

每个租户 `uni_documents` 表安装 `AFTER INSERT OR UPDATE OR DELETE` 触发器
`emit_search_outbox`，调用公共函数 `public.emit_search_outbox()`：

| 业务操作 | 生成事件 |
| --- | --- |
| INSERT | `upsert` |
| UPDATE 且 `is_delete=false` | `upsert` |
| UPDATE 且 `is_delete=true` | `delete` |
| DELETE | `delete` |

业务行变更与 outbox 写入在同一数据库事务内完成，业务提交则事件提交，业务回滚则事件回滚。

### 5.3 Debezium 配置

部署配置：

- connector：`pg-search-outbox-connector`
- slot：`unidata_search_outbox_slot`
- publication：`unidata_search_outbox_pub`
- `table.include.list=public.search_outbox`
- `plugin.name=pgoutput`
- `snapshot.mode=always`
- Kafka topic：`pg.public.search_outbox`

相关文件：

- `docker/register-connector.sh`
- `docker-compose.yml`
- `meilisearch-sync-service/.env.example`

Debezium 不再直接监听租户业务表；租户业务表变更必须先通过触发器进入公共 outbox。

### 5.4 Go 同步服务

`meilisearch-sync-service/internal/service/sync.go`：

- 识别 `payload.after.operation` 作为 outbox 事件。
- upsert 必须携带 `document`，并强制注入 `id`、`app_id`、`collection`。
- delete 只删除当前事件租户 index 中的当前文档。
- `ResolveIndex()` 根据 `app_id + collection` 重新计算 index UID，不信任消息中的 `index_uid`。
- 缺少 `app_id` / `collection` / `document_id` 或 operation 非法时进入 DLQ。
- 日志记录 app_id 和 collection，不记录完整业务文档。

命令处理 `MeiliCommandHandler`：

- 校验命令中的 `index_uid` 与 `model.IndexUID(app_id, collection)` 一致。
- 不一致的命令直接进入永久错误/DLQ。
- 支持 `update_settings` 与 `delete_index`，只操作当前租户当前集合的 index。

当前幂等策略依赖 Kafka at-least-once 语义加 Meilisearch upsert/delete 的天然幂等；
`event_id` 已进入事件模型，但尚未实现独立去重表，见第 11 节。

---

## 6. Meilisearch 索引与搜索代理

索引命名从旧的 `app_name_collection` 改为：

```text
t_<sha256(app_id)[:16]>__<collection>
```

搜索请求要求：

- 租户 A 的 API Key 只能访问租户 A 的 index。
- 请求路径中的 collection 只代表集合名，不允许客户端传入完整 index UID。
- 不开放 Meilisearch 原始地址或 master key。
- 后端代理统一使用服务端 Meilisearch API Key。
- index 不存在时返回租户范围内的 `SEARCH_INDEX_NOT_FOUND`，不暴露其他租户信息。

索引设置命令升级为 v2 协议：

```json
{
  "version": 2,
  "command_id": "t_<hash>__items:1700000000",
  "app_id": "...",
  "collection": "items",
  "index_uid": "t_<hash>__items",
  "action": "update_settings",
  "payload": {
    "filterableAttributes": [],
    "sortableAttributes": []
  },
  "ts": 0
}
```

相关文件：

- `UniData/app/services/index_service.py`
- `meilisearch-sync-service/internal/model/model.go`
- `meilisearch-sync-service/internal/handler/search_v1.go`

---

## 7. 应用与租户生命周期

### 7.1 创建应用

`OpenPlatformService.create_app()` 流程：

1. 写入 `open_platform_apps` 并 flush。
2. 根据 `app_id` 计算 schema 名。
3. 调用 `provision_tenant()`：
   - 确保 `public.search_outbox` 存在
   - `CREATE SCHEMA`
   - 创建 `uni_documents` 表、索引、约束
   - 启用/强制 RLS
   - 创建 CDC 触发器
4. 写 `app.upsert` outbox 事件。
5. 写审计日志。
6. 请求事务提交后才对外可见。

创建失败时，schema、表、应用记录在同一事务中整体回滚。
`provision_tenant()` 幂等，可安全重试。

### 7.2 删除应用

新增接口：

```text
DELETE /api/v1/open-platform/apps/{app_id}
```

`OpenPlatformService.delete_app()` 流程：

1. 应用状态置为 `deleting`，立即拒绝新的 API Key 请求。
2. 撤销该应用下全部 active Key，并写 `key.revoked` 事件。
3. 从租户 schema 列出 collection。
4. 对每个 collection 发送 `delete_index` Kafka 命令。
5. 删除租户 schema（CASCADE）。
6. 应用状态置为 `deleted`，写 `app.upsert` 事件。
7. 写 `app.delete` 审计，审计 details 包含已回收的 collections。

说明：

- API Key 鉴权在 Python 与 Go 都要求 `app.status == "active"` 且 key 为 active，
  因此 `deleting` 状态能立即切断数据写入和搜索。
- 删除索引命令发送失败不会阻断 schema 回收，失败会留在审计记录中，便于人工补发重试。
- 前端控制台在应用详情页提供删除入口，删除后跳回应用列表。

相关文件：

- `UniData/app/services/open_platform_service.py`
- `UniData/app/api/v1/endpoints/open_platform.py`
- `open-platform-web/src/pages/AppDetailPage.tsx`
- `open-platform-web/src/api/client.ts`

---

## 8. 数据库角色与部署

为了让 RLS 真正生效，业务账号不能是超级用户。初始化脚本：

```text
docker/postgres-init/01-create-unidata-roles.sh
```

脚本创建两个角色：

| 角色 | 用途 | 权限 |
| --- | --- | --- |
| `unidata_app` | UniData 业务写入/DDL | LOGIN；数据库 CONNECT+CREATE；public schema USAGE+CREATE；默认所有业务表由其拥有 |
| `unidata_cdc` | Debezium 逻辑复制 | LOGIN+REPLICATION；数据库 CONNECT+CREATE；public schema USAGE；`unidata_app` 在 public 新表的 SELECT 默认权限 |

`unidata_app` 创建租户 schema/表后是所有者，`FORCE RLS` 对其同样生效；
`unidata_cdc` 只读取 `public.search_outbox`，不访问租户业务表。

注意：

- 该脚本只在 PostgreSQL 数据目录首次初始化时执行。
- 已有数据卷不会自动重跑；需要重建数据卷，或手动创建角色并授予相同权限。
- `.env.docker` 需要配置 `UNIDATA_PG_USER/UNIDATA_PG_PASSWORD/CDC_PG_USER/CDC_PG_PASSWORD`，
  并把 `PG_CONN_STRING` 指向 `unidata_app`。
- `register-connector.sh` 使用 `CDC_PG_USER` 连接 PostgreSQL，不再使用业务账号。

相关文件：

- `docker-compose.yml`
- `.env.docker.example`
- `docker/register-connector.sh`

---

## 9. 迁移

迁移脚本：`UniData/migrations/migrate_physical_tenancy.py`

执行步骤：

1. 检查 `unidata_schema_migrations` 中是否已存在
   `20260805_physical_tenancy`，已存在则跳过。
2. 确保 `public.search_outbox` 存在。
3. 读取旧 `public.uni_documents` 中所有去重后的 `app_id`。
4. 对每个 `app_id`：
   - 校验对应 `open_platform_apps` 存在，缺失租户直接报错，禁止静默归入默认租户。
   - `provision_tenant()` 创建目标 schema。
   - 事务内设置 `app.tenant_id`，按 `app_id` 复制数据。
   - 校验源/目标行数、`(collection, id)` 去重数、`is_delete` 数量一致，不一致即失败。
5. 写入迁移版本记录。

迁移完成后：

- 部署新 Debezium connector 和同步服务。
- 使用新 consumer group 从 `public.search_outbox` 快照构建租户 index。
- 对比每租户每 collection 的 PostgreSQL 与 Meilisearch 文档数。
- 切换搜索代理到新的 index UID 规则。
- 旧 `public.uni_documents` 和旧 `app_name_collection` index 保留只读回滚窗口，
  验证完成后由运维删除。

约束：

- 两个租户拥有相同 `id` 不会冲突，因为目标是不同 schema。
- 旧表 `app_name` 不作为租户主键。
- 脚本幂等，失败可清理目标 schema 后重跑。

---

## 10. 测试

### Python 单元测试

- `UniData/tests/test_physical_tenancy_unit.py`
- `UniData/tests/test_document_tenancy_unit.py`

覆盖命名稳定性、非法 collection、schema translate map、事务上下文、
RLS/trigger DDL、迁移幂等。

### PostgreSQL 集成测试

- `UniData/tests/test_physical_tenancy_integration.py`
- `UniData/tests/test_document_tenancy_integration.py`
- `UniData/tests/test_document_tenancy_migration.py`

覆盖：

- 两个租户复用相同 `(collection, id)`。
- 非超级用户角色绕过 repository 直接查询/更新/插入其他租户 schema 被 RLS 拦截。
- 触发器对 insert、软删除、硬删除分别生成正确 outbox 事件。
- outbox 与业务数据同事务提交/回滚。
- 租户 provisioning 幂等，创建失败整体回滚。
- 连接池/会话复用不残留租户上下文。
- 删除应用撤销 Key、回收 schema、写审计。

运行方式：

```bash
cd UniData
TEST_PG_CONN_STRING=postgres://postgres:...@127.0.0.1:5432/unidata_test \
  .venv/bin/python -m pytest -q
```

### Go 测试

```bash
cd meilisearch-sync-service
go test ./...
```

覆盖 `IndexUID` 稳定性、租户索引隔离、outbox 解析、缺失路由字段进 DLQ、
命令 `index_uid` 不匹配拒绝、删除事件不跨租户。

### 前端

```bash
cd open-platform-web
npm run build
```

---

## 11. 运维注意事项与后续工作

### 已落地但需人工关注的运维点

- 已有 PostgreSQL 数据卷不会自动执行角色初始化脚本；升级时必须手工建角色和授权，
  或重建数据卷。
- 当前本地 Docker 栈仍可能在旧 connector 配置下运行；应用新配置前需要重建
  `connect-init` 并确认 connector 名称为 `pg-search-outbox-connector`。
- 删除应用对 Meilisearch 删除命令是尽力而为；命令失败不会回滚 schema，需要根据
  `app.delete` 审计记录人工补发。

### 尚未自动化的后续工作

- `search_outbox` 保留与清理：需要结合 Kafka consumer 消费进度、最小保留时间、
  失败重试状态做清理，不能直接按时间删除尚未消费的事件。
- 事件级幂等去重：当前依赖 Kafka at-least-once + Meilisearch 幂等；`event_id`
  尚未接入独立去重表。
- 全量重建的自动校验/切换：迁移已校验复制一致性，但 Meilisearch 重建、文档数比对、
  index 切换和旧资源清理仍由运维执行。

---

## 12. 文件索引

| 模块 | 文件 |
| --- | --- |
| 租户命名/上下文 | `UniData/app/core/tenant.py` |
| 租户 schema/RLS/outbox/trigger | `UniData/app/services/tenant_service.py` |
| 文档仓储 | `UniData/app/repositories/document_repository.py` |
| 索引命令 v2 | `UniData/app/services/index_service.py` |
| 应用生命周期 | `UniData/app/services/open_platform_service.py` |
| 删除接口 | `UniData/app/api/v1/endpoints/open_platform.py` |
| 物理迁移 | `UniData/migrations/migrate_physical_tenancy.py` |
| Go 命名/模型 | `meilisearch-sync-service/internal/model/model.go` |
| Go 同步/命令处理 | `meilisearch-sync-service/internal/service/sync.go`、`handlers.go` |
| Go 搜索代理 | `meilisearch-sync-service/internal/handler/search_v1.go` |
| Debezium 注册 | `docker/register-connector.sh` |
| 数据库角色初始化 | `docker/postgres-init/01-create-unidata-roles.sh` |
| 环境示例 | `.env.docker.example`、`meilisearch-sync-service/.env.example` |
| 测试 | `UniData/tests/test_physical_tenancy_*.py`、`meilisearch-sync-service/internal/**/*_test.go` |

