# 租户物理隔离实现（app_id 维度）

> 描述当前已落地的「按开放平台应用做 PostgreSQL 与 Meilisearch 物理隔离」实现。
> 适用提交：`5e991f3`(物理租户 schema 隔离) / `6deaa61`(sync 适配 outbox CDC) 起。
> 代码为唯一事实来源；本文描述设计约束、关键位置与运维注意点。

## 1. 背景与目标

原实现把所有应用文档写入 `public.uni_documents`、索引名由 `app_name + collection` 推导，存在：应用改名致索引漂移、跨租户仅靠应用层过滤、CDC 直连业务表易误同步等问题。

本次以 `OpenPlatformApp` 为租户边界、`app_id` 为不可变标识：

- **PostgreSQL**：每应用独立 schema，表级 RLS，事务内设置租户上下文。
- **CDC**：租户表经事务触发器把变更写入公共 `public.search_outbox`，Debezium 只监听 outbox。
- **Meilisearch**：每 `(app_id, collection)` 独立 index，UID 由 `app_id` 稳定推导。
- **搜索代理**：API Key 解析出的 `app_id` 决定可访问 index，不信任客户端传入的索引名。
- **生命周期**：建应用自动初始化租户资源；删应用冻结鉴权、撤销 Key、删索引、回收 schema。
- `app_name` 仅作展示/兼容，不再参与安全边界。

## 2. 总体架构

```text
API Key / 控制台
       │
       ▼
UniData (FastAPI)
  ├─ 控制面：open_platform_apps / api_keys / collection_settings / outbox / 审计
  └─ 租户面：tenant_<hash(app_id)>.uni_documents（RLS + CDC trigger）
       │ 同事务写入
       ▼
public.search_outbox（公共 CDC 传输表，非业务主存储）
       │ Debezium（pgoutput，仅 public.search_outbox）
       ▼
Kafka topic: pg.public.search_outbox
       │
       ▼
meilisearch-sync-service (Go)
  ├─ outbox 解析：app_id + collection + document_id + operation
  ├─ 命令处理：update_settings / delete_index，校验 index_uid 与租户路由一致
  └─ 搜索代理：按 API Key 的 app_id 路由到 t_<hash(app_id)>__<collection>
       │
       ▼
Meilisearch（每租户每集合独立 index）
```

公共 outbox 是 CDC 传输层，不是业务主存储，通过数据库权限、网络隔离与审计保护，业务 API 不直接读写它。

## 3. 租户身份与命名

统一逻辑位于 `UniData/app/core/tenant.py`，Python 与 Go 算法一致。

| 资源 | 规则 | 示例 |
| --- | --- | --- |
| PostgreSQL schema | `tenant_` + `sha256(app_id)[:32]` | `tenant_90f374a04c60...` |
| Meilisearch index | `t_` + `sha256(app_id)[:16]` + `__` + collection | `t_9b31c0a8__orders` |

约束：

- 只用 `app_id` 推导，应用改名不改变 schema/index。
- collection 须匹配 `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`，拒绝 SQL 标识符注入与路径穿越。
- schema 名进 DDL 前再校验，只允许 `tenant_` 前缀加十六进制字符。
- 同 `app_id` 始终同名；不同 `app_id` 即使内容相同也生成不同名。

Go 侧：`model.IndexUID(appID, collection)`（`internal/model/model.go`）、搜索代理按 `identity.AppID` 路由（`internal/handler/search_v1.go`）、同步按事件 `app_id` 路由（`internal/service/sync.go`）。

## 4. PostgreSQL 租户模型

### 4.1 控制面（public schema，不按租户拆分）

`open_platform_apps`、`api_keys`、`collection_settings`、`open_platform_audit_logs`、`open_platform_outbox`、`search_outbox`、`unidata_schema_migrations`。

### 4.2 租户 schema

每应用独立 schema（如 `tenant_90f374a0...`），含 `uni_documents` 表：字段 `row_id(UUID PK)`、`id`、`app_id`、`collection`、`app_name`、`payload(JSONB)`、`is_delete`、`created_at`、`updated_at`；约束 `UNIQUE(app_id, collection, id)`、`FK(app_id)→open_platform_apps ON DELETE RESTRICT`、`CHECK(app_id='<当前租户>')`；`REPLICA IDENTITY FULL` 保证删除事件含完整路由字段。

### 4.3 RLS

租户表 `ENABLE` + `FORCE ROW LEVEL SECURITY`，策略 `USING/WITH CHECK (app_id = current_setting('app.tenant_id', true))`。

访问原则：API Key 鉴权只查控制面；文档 CRUD/集合统计/索引管理必须走租户上下文；管理员访问租户数据也须显式指定 `app_id`；**业务数据库角色须为普通角色（非超级用户），否则 RLS 被绕过**。

### 4.4 事务上下文

`tenant.py` 的 `set_tenant_context()` 在每个租户操作前执行 `set_config('app.tenant_id', :app_id, true)` + `SET LOCAL search_path`；均为事务级设置，连接归还连接池后不残留。ORM 用 `schema_translate_map={None: tenant_schema}` 绑定当前 schema。仓储入口 `document_repository.py` 先 `ensure_tenant()` 再 `set_tenant_context()`；控制面查询不经过该入口。

## 5. CDC Outbox

`public.search_outbox`（`ensure_search_outbox()` 幂等创建/修复）字段：`event_id`、`app_id`、`collection`、`document_id`、`operation`(upsert/delete)、`document`(JSONB)、`event_version`(BIGINT 序列)、`created_at`。`app_id/collection/document_id` 为强制路由字段，缺失触发器的 DDL 直接报错。

触发器 `emit_search_outbox`（`AFTER INSERT/UPDATE/DELETE`）调公共函数 `public.emit_search_outbox`：INSERT/UPDATE(`is_delete=false`)→`upsert`；UPDATE(`is_delete=true`)/DELETE→`delete`。业务行变更与 outbox 写入同事务，提交/回滚一致。

Debezium 配置：connector `pg-search-outbox-connector`、slot `unidata_search_outbox_slot`、publication `unidata_search_outbox_pub`、`table.include.list=public.search_outbox`、`plugin.name=pgoutput`、`snapshot.mode=always`、topic `pg.public.search_outbox`（见 `docker/register-connector.sh`、`meilisearch-sync-service/.env.example`）。Debezium 不再直连租户业务表。

Go 同步（`internal/service/sync.go`）：识别 `payload.after.operation`；upsert 强制注入 `id/app_id/collection`，delete 只删当前租户 index 的当前文档；`ResolveIndex()` 由 `app_id+collection` 重算 index UID，不信任消息中的 `index_uid`；缺路由字段/非法 operation 进 DLQ；日志记 app_id/collection 不记完整业务文档。`MeiliCommandHandler` 校验命令 `index_uid` 与 `model.IndexUID(app_id, collection)` 一致，否则进永久错误/DLQ；支持 `update_settings`/`delete_index`。幂等当前依赖 Kafka at-least-once + Meilisearch upsert/delete 天然幂等（`event_id` 已进事件模型，去重表未实现，见 §11）。

## 6. Meilisearch 索引与搜索代理

索引命名：`t_<sha256(app_id)[:16]>__<collection>`。

代理要求：租户 A 的 Key 只能访问租户 A 的 index；路径中的 collection 只表集合名，不允许客户端传完整 index UID；不开放 Meilisearch 原始地址/master key；后端代理统一用服务端 Key；index 不存在返回租户内 `SEARCH_INDEX_NOT_FOUND`，不暴露其他租户。索引设置命令升级为 v2 协议（`version`/`command_id`/`app_id`/`collection`/`index_uid`/`action`/`payload`），相关：`UniData/app/services/index_service.py`、`meilisearch-sync-service/internal/model/model.go`、`internal/handler/search_v1.go`。

## 7. 应用与租户生命周期

**创建**（`open_platform_service.create_app`）：写 `open_platform_apps`→`provision_tenant()`（确保 outbox + `CREATE SCHEMA` + 建表/索引/约束 + 启用 RLS + 装 CDC 触发器）→写 `app.upsert` outbox→写审计→事务提交后可见。失败整体回滚；`provision_tenant()` 幂等可重试。

**删除**（`DELETE /api/v1/open-platform/apps/{app_id}`）：状态置 `deleting`（立即拒绝新 Key）→撤销全部 active Key 并写 `key.revoked`→列 collection 发 `delete_index` Kafka 命令→`CASCADE` 删 schema→状态置 `deleted`+写 `app.delete` 审计（details 含已回收 collections）。`deleting` 状态因 API Key 鉴权要求 `app.status=='active'` 而立即切断写入/搜索；删索引命令失败不阻断 schema 回收，失败留审计待人工补发。前端入口在应用详情页。

## 8. 数据库角色与部署

RLS 真正生效要求业务账号非超级用户。初始化脚本 `docker/postgres-init/01-create-unidata-roles.sh` 建两角色：

| 角色 | 用途 | 权限 |
| --- | --- | --- |
| `unidata_app` | 业务写入/DDL | LOGIN；CONNECT+CREATE；public USAGE+CREATE；业务表所有者（FORCE RLS 同样生效） |
| `unidata_cdc` | Debezium 逻辑复制 | LOGIN+REPLICATION；CONNECT+CREATE；public USAGE；对 public 新表 SELECT 默认权限 |

注意：脚本仅 PostgreSQL 数据目录首次初始化时执行；已有数据卷不自动重跑，需重建数据卷或手动建角色授权。`.env.docker` 需配 `UNIDATA_PG_USER/PASSWORD`、`CDC_PG_USER/PASSWORD`，`PG_CONN_STRING` 指向 `unidata_app`；`register-connector.sh` 用 `CDC_PG_USER` 连接。

## 9. 迁移

脚本 `UniData/migrations/migrate_physical_tenancy.py`：检查 `unidata_schema_migrations` 中 `20260805_physical_tenancy`，已存在则跳过；确保 outbox；读旧 `public.uni_documents` 去重 `app_id`；逐租户校验 `open_platform_apps` 存在（缺失报错，禁止静默归入默认租户）→`provision_tenant()`→事务内设 `app.tenant_id` 复制数据→校验源/目标行数、`(collection,id)` 去重数、`is_delete` 数一致；写迁移版本。幂等，失败可清目标 schema 重跑。

完成后：部署新 Debezium connector 与新 consumer group 从 outbox 快照构建租户 index；比对每租户每 collection 的 PG 与 Meilisearch 文档数；切换搜索代理到新 index UID 规则；旧表/旧索引保留只读回滚窗口，验证后由运维删除。

## 10. 测试

- Python：`tests/test_physical_tenancy_unit.py`、`test_document_tenancy_unit.py`、`test_physical_tenancy_integration.py`、`test_document_tenancy_integration.py`、`test_document_tenancy_migration.py`——覆盖命名稳定性、非法 collection、schema translate、事务上下文、RLS/trigger DDL、迁移幂等、RLS 拦非超户跨租户直查、触发器事件、outbox 同事务、provisioning 回滚、上下文不残留、删应用回收。
  ```bash
  cd UniData && TEST_PG_CONN_STRING=postgres://...@127.0.0.1:5432/unidata_test pytest -q
  ```
- Go：`cd meilisearch-sync-service && go test ./...`——覆盖 `IndexUID` 稳定性、租户索引隔离、outbox 解析、缺路由字段进 DLQ、命令 `index_uid` 不匹配拒绝、删除不跨租户。
- 前端：`cd open-platform-web && npm run build`。

## 11. 运维注意与后续工作

**已落地需人工关注**：

- 已有数据卷不自动执行角色初始化脚本；升级须手工建角色授权或重建数据卷。
- 本地栈可能仍在旧 connector 配置下运行；应用新配置前需重建 `connect-init` 并确认 connector 名 `pg-search-outbox-connector`。
- 删应用对 Meilisearch 删除命令为尽力而为；失败不回滚 schema，需据 `app.delete` 审计人工补发。

**尚未自动化**：

- `search_outbox` 保留与清理：需结合 Kafka 消费进度/最小保留时间/失败重试状态，不能直接按时间删未消费事件。
- 事件级幂等去重：当前依赖 Kafka at-least-once + Meilisearch 幂等；`event_id` 未接入独立去重表。
- 全量重建的自动校验/切换：迁移已校验复制一致性，但 Meilisearch 重建、文档数比对、index 切换与旧资源清理仍由运维执行。

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
