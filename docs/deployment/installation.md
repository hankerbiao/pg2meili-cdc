# 安装步骤

本指南将带领您完成 UniData 系统的完整部署流程。建议按照以下顺序进行操作。

## 1. 部署开源基础组件

首先搭建数据存储、消息流转和搜索引擎基础设施。推荐使用 Docker Compose 快速启动。

### 1.1 准备 Docker Compose 文件

创建一个 `docker-compose.yml` 文件（项目中通常已提供），包含 Zookeeper, Kafka, Debezium Connect 和 Meilisearch。

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
  
  meilisearch:
    image: getmeili/meilisearch:v1.8
    ports: ["7700:7700"]
    volumes:
      - ./meili_data:/meili_data
    command: meilisearch --master-key="my_master_key"
```

### 1.2 启动服务

```bash
docker-compose up -d
```

## 2. 配置 PostgreSQL

作为 CDC 的数据源，PostgreSQL 必须配置逻辑复制功能。

### 2.1 修改 `postgresql.conf`

```ini
# 开启逻辑复制
wal_level = logical
# 允许的最大复制槽数量
max_replication_slots = 5
# 允许的最大 WAL 发送进程数
max_wal_senders = 5
```

### 2.2 修改 `pg_hba.conf`

确保 Debezium Connect 容器或服务能够访问 PostgreSQL。

```text
# 允许 Docker 容器网段或特定 IP 访问
host    all             all             10.0.0.0/8              scram-sha-256
```

### 2.3 重启 PostgreSQL

```bash
sudo systemctl restart postgresql
# 验证配置
psql -U postgres -c "SHOW wal_level;" # 结果应为 logical
```

## 3. 注册 Debezium Connector

用于监听 PostgreSQL 变更并发送到 Kafka。

### 执行注册命令

```bash
curl -i -X POST -H "Accept:application/json" -H "Content-Type:application/json" \
localhost:8083/connectors/ -d '{
  "name": "meili-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "host.docker.internal", 
    "database.port": "5432",
    "database.user": "postgres",           
    "database.password": "你的密码", 
    "database.dbname": "postgres",        
    "topic.prefix": "search_sync",
    "table.include.list": "public.payload", 
    "plugin.name": "pgoutput",
    "column.include.list": "public.payload.(id,title,content,category,is_delete)"
  }
}'
```

## 4. 部署 UniData 服务 (API)

UniData 负责数据写入和管理。

### 4.1 获取代码

```bash
git clone https://github.com/hankerbiao/pg2meili-cdc.git
cd pg2meili-cdc/UniData
```

### 4.2 安装依赖 (推荐 uv)

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

### 4.3 启动服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

## 5. 部署 Sync Service (Go Agent)

部署在各地区边缘节点的同步程序，消费 Kafka 并写入 Meilisearch。

### 5.1 获取与编译

```bash
cd meilisearch-sync-service
go build -o sync-service main.go
```

### 5.2 运行服务

```bash
# 设置必要环境变量（详见配置文档）
export UNIDATA_URL="http://10.32.129.188:8080"
export HTTP_ADDR=":8091"

# 启动
./sync-service
```
