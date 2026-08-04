# Docker 部署评审报告

评审对象：`docker-compose.yml`、`Dockerfile`、`docker/kafka-init.sh`、`.env.docker(.example)`、`README.md` 部署章节，以及与部署相关的 `UniData` / `meilisearch-sync-service` 配置。

评审日期：2026-08-03

---

## 总体结论

部署脚手架整体结构清晰、安全基线合格（端口绑定 127.0.0.1、非 root 运行、逻辑解码参数正确、compose watch/healthcheck 基本到位）。但存在 **1 个阻断性功能缺口** 和 **若干中等可靠性问题**，直接 `docker compose up -d` 后 CDC 链路并不会真正打通。

---

## 问题清单（按严重度）

| 严重度 | 位置 | 问题 | 建议 |
| --- | --- | --- | --- |
| 🔴 阻断 | 全链路 | **Debezium Connector 从未注册**。架构核心是 CDC，但 compose 只起了一个空的 `connect` 容器，没有任何脚本/服务向 `connect:8083/connectors` 注册 PostgreSQL source connector。`docker compose up -d` 后数据不会从 PG 进入 Kafka，整条同步链路断在第一环。README 部署章节也未提及。 | 增加 `connect-init` 一次性服务 + 注册脚本（见下方方案），并在 README 说明。 |
| 🔴 阻断 | `Dockerfile:29` | `UV_DEFAULT_INDEX=${PYTHON_PACKAGE_INDEX}` 不是 uv 的合法环境变量（合法为 `UV_INDEX_URL`），属于误导性配置。当前因 `uv pip install --index-url` 已显式指定，不影响构建，但易误判。 | 删除该行，保留 `UV_INDEX_URL` 即可。 |
| 🟡 中等 | `docker-compose.yml:40-52` | **redis 是死配置**。中心服务 `UniData` 代码完全不引用 redis（已 grep 确认）；redis 仅被 *独立部署* 的 `meilisearch-sync-service` 使用。compose 内无任何服务 `depends_on` 它，也无环境变量引用。 | 要么删除并注明 redis 服务于容器外 Agent；要么将 sync service 也纳入 compose。 |
| 🟡 中等 | `docker-compose.yml:128-136` | **meilisearch 缺 healthcheck**。作为关键下游无就绪探测，compose 层面无法保证其就绪，且无法被其他服务 `depends_on`。 | 添加 `curl`-based healthcheck（`/health`）。 |
| 🟡 中等 | `docker-compose.yml:116-126` | **kafka-ui 使用 `:latest` 标签**，不可复现。其余中间件均固定版本（debezium:2.4、postgres:16、meilisearch:v1.8），唯独此处用 latest。 | 固定版本，如 `provectuslabs/kafka-ui:v0.7.2`。 |
| 🟡 中等 | `docker-compose.yml:99-114` | **connect 无 healthcheck、无显式依赖 kafka healthy**。当前靠 `kafka-init` 链式依赖间接保证，但 connect 自身就绪状态外部不可探测；注册 connector 前难以判断。 | 添加 healthcheck；或文档明确要求注册前确认 connect 已起。 |
| 🟢 轻微 | `docker-compose.yml:54-58` | zookeeper 无 healthcheck，仅 `service_started`。 | 可加 `zkServer.sh status` healthcheck（低风险）。 |
| 🟢 轻微 | `docker/kafka-init.sh:25-31` | `api_keys.events` 创建时已带 `--config cleanup.policy=compact`，随后又 `kafka-configs.sh --alter` 重复设置一次，冗余。 | 保留其一即可。 |
| 🟢 轻微 | `docker-compose.yml:1` | `name: pg2meili` 与仓库名 `pg2meili-cdc`、README「异地分布式搜索架构系统」命名不一致，仅影响 compose 项目名。 | 统一命名（非必须）。 |
| 🟢 轻微 | `Dockerfile` / 平台 | `debezium/kafka:2.4` 主要为 amd64；Apple Silicon 上 `up` 会拉 amd64 镜像跑 Rosetta（慢），部署到 amd64 服务器则正常。 | 在 README/compose 注明目标平台（如 `platform: linux/amd64`）。 |
| 🟢 建议 | `docker-compose.yml:KAFKA_EXTERNAL_HOST` | 远程 Go Agent 接入需将 `KAFKA_EXTERNAL_HOST` 改为宿主可达地址，OUTSIDE listener 映射到 127.0.0.1，跨机访问需调整。 | 补充防火墙/安全组说明与示例。 |

---

## 关键缺口详解：Debezium Connector 注册

当前 `connect` 容器启动后只是 Kafka Connect worker，必须有 connector 才能真正捕获 PG 变更。建议补充以下两部分。

### 1) 注册脚本 `docker/register-connector.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

CONNECT_URL="${CONNECT_URL:-http://connect:8083}"
# 密码取自 compose 注入的环境变量
PG_PASSWORD="${POSTGRES_PASSWORD:-change-me}"

until curl -fsS "${CONNECT_URL}/" >/dev/null 2>&1; do
  echo "等待 Kafka Connect 就绪: ${CONNECT_URL}"
  sleep 3
done

CONNECTOR_JSON=$(cat <<EOF
{
  "name": "pg-cdc-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "${POSTGRES_USER:-postgres}",
    "database.password": "${PG_PASSWORD}",
    "database.dbname": "${POSTGRES_DB:-postgres}",
    "database.server.name": "pg",
    "schema.include.list": "public",
    "table.include.list": "public.documents",
    "plugin.name": "pgoutput",
    "publication.autocreate.mode": "filtered",
    "slot.name": "unidata_slot",
    "topic.prefix": "pg",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "false"
  }
}
EOF
)

# 已存在则先删后建，幂等
curl -fsS -X DELETE "${CONNECT_URL}/connectors/pg-cdc-connector" >/dev/null 2>&1 || true
curl -fsS -X POST "${CONNECT_URL}/connectors" \
  -H "Content-Type: application/json" \
  -d "${CONNECTOR_JSON}"
echo "Debezium connector 已注册"
```

### 2) compose 中增加 `connect-init` 服务

```yaml
  connect-init:
    image: curlimages/curl:latest
    restart: "no"
    environment:
      <<: *unidata-environment
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-change-me}
    volumes:
      - ./docker/register-connector.sh:/opt/unidata/register-connector.sh:ro
    entrypoint: ["/bin/sh", "/opt/unidata/register-connector.sh"]
    depends_on:
      connect:
        condition: service_started
      postgres:
        condition: service_healthy
```

> 注意：`table.include.list` 需与实际业务表名对齐（当前示例为 `public.documents`），变更表列表应随业务调整。

---

## 做得好的地方（应保留）

- 端口全部绑定 `127.0.0.1`，避免中间暴露；Kafka 内/外 listener 分离设计合理。
- PostgreSQL 以 `command` 数组形式设置 `wal_level=logical` + 复制槽参数，逻辑解码前置条件正确。
- `unidata` 服务设置 `init: true`（正确转发信号、回收僵尸进程）。
- 运行镜像使用非 root 用户（uid 10001），`USER unidata` 合理。
- 默认密钥集中在 `.env.docker.example` 并明确要求替换；`.gitignore` 已忽略 `.env.*`，敏感文件不会误提交。
- Kafka topic 初始化用独立一次性容器 + `service_completed_successfully` 依赖链，拓扑顺序正确（zookeeper → kafka → kafka-init → connect/unidata）。

---

## 修复优先级建议

1. **必须先做**：注册 Debezium connector（阻断性）。
2. **建议同批做**：移除 `UV_DEFAULT_INDEX`、固定 kafka-ui 版本、补 meilisearch/connect healthcheck、清理 redis 死配置。
3. **可选增强**：zookeeper healthcheck、命名统一、目标平台声明、远程接入网络说明。

---

## 待确认事项

- `table.include.list` 的真实业务表集合（影响 connector 配置正确性）。
- redis 是否确实只服务于容器外 sync agent；若是，建议显式注释说明，避免后续误删或误以为缺失。
- sync service（Go Agent）是否有计划纳入中心 compose，还是长期保持各区域独立部署（README 已说明后者，需与 redis 配置对齐表述）。
