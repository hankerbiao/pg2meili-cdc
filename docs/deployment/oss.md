# 开源组件部署

本章节详细说明架构中涉及的开源中间件部署步骤，包括数据库、消息队列和搜索引擎。

## 1. PostgreSQL (数据源)

作为 CDC 的数据源，必须配置逻辑复制功能。

### 1.1 修改配置文件 (`postgresql.conf`)

```ini
# 开启逻辑复制
wal_level = logical
# 允许的最大复制槽数量
max_replication_slots = 5
# 允许的最大 WAL 发送进程数
max_wal_senders = 5
```

### 1.2 修改访问权限 (`pg_hba.conf`)

注意：以下示例仅适用于测试环境。生产环境请改为内网网段或指定应用主机 IP。

```text
# 允许内网网段访问（示例）
host    all             all             10.0.0.0/8              scram-sha-256
# 或者指定应用主机（示例）
# host  all             all             10.12.34.56/32          scram-sha-256
```

### 1.3 重启验证

```bash
sudo systemctl restart postgresql
psql -U postgres -c "SHOW wal_level;" # 结果应为 logical
```

## 2. Kafka & Debezium (消息中间件)

使用 Docker Compose 部署 Zookeeper、Kafka 和 Debezium Connect。

建议固定版本以保证环境可复现（示例使用 Debezium 2.4 组合）。

### 2.1 `docker-compose.yml`

```yaml
version: '3.8'
services:
  zookeeper:
    image: quay.io/debezium/zookeeper:2.4
    ports: ["2181:2181"]

  kafka:
    image: quay.io/debezium/kafka:2.4
    ports: ["9092:9092"]
    environment:
      - ZOOKEEPER_CONNECT=zookeeper:2181
    depends_on: [zookeeper]

  connect:
    image: quay.io/debezium/connect:2.4
    ports: ["8083:8083"]
    environment:
      - BOOTSTRAP_SERVERS=kafka:9092
      - GROUP_ID=1
      - CONFIG_STORAGE_TOPIC=my_connect_configs
      - OFFSET_STORAGE_TOPIC=my_connect_offsets
      - STATUS_STORAGE_TOPIC=my_connect_statuses
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on: [kafka]
```

### 2.2 启动服务

```bash
docker-compose up -d
```

## 3. Meilisearch (搜索引擎)

部署 Meilisearch 服务端及其管理控制台。

建议固定版本以保证环境可复现（示例使用 `getmeili/meilisearch:v1.8`）。

### 3.1 启动服务端

```bash
docker run -d -p 7700:7700 \
  -v $(pwd)/meili_data:/meili_data \
  --name meilisearch \
  getmeili/meilisearch:v1.8 \
  meilisearch --master-key="my_master_key"
```

### 3.2 启动控制台 (Meilisearch UI)

```bash
docker pull eyeix/meilisearch-ui:latest

docker run -d --restart=on-failure:5 \
  --name="meilisearch-ui" \
  -p 24900:24900 \
  eyeix/meilisearch-ui:latest
```
