这是一份为您整理的完整部署文档。它涵盖了从 PostgreSQL 底层配置到 Kafka/Debezium 环境搭建，再到 Go 消费者逻辑实现的完整链路。

---

# 异地搜索增强架构部署文档 (PostgreSQL + Debezium + Kafka + Meilisearch)

本方案通过 **CDC (Change Data Capture)** 技术，实现 PostgreSQL 数据的近实时异地同步。PostgreSQL 作为真相源，各区域的 Meilisearch 作为边缘搜索节点，提升全球搜索性能。

---

## 1. PostgreSQL 宿主机配置 (数据源层)

在开启 CDC 之前，必须配置 PostgreSQL 的逻辑复制功能。

### 1.1 修改配置文件

找到 `postgresql.conf`（通常在 `/etc/postgresql/16/main/`），修改以下参数：

```ini
# 开启逻辑复制
wal_level = logical
# 允许的最大复制槽数量
max_replication_slots = 5
# 允许的最大 WAL 发送进程数
max_wal_senders = 5

```

### 1.2 修改访问权限

找到 `pg_hba.conf`，允许 Docker 网段访问：

```text
# 允许所有地址通过密码连接（生产环境建议限制为具体网段）
host    all             all             0.0.0.0/0               scram-sha-256

```

### 1.3 重启服务并检查

```bash
sudo systemctl restart postgresql

# 检查配置是否生效
psql -U postgres -c "SHOW wal_level;" # 结果应为 logical

```

---

## 2. 消息中心与同步引擎部署 (中转层)

使用 Docker Compose 部署 Zookeeper、Kafka 和 Debezium Connect。

### 2.1 编写 `docker-compose.yml`

```yaml
version: '3.8'
services:
  zookeeper:
    image: quay.io/debezium/zookeeper:2.4
    container_name: zookeeper
    ports:
      - "2181:2181"

  kafka:
    image: quay.io/debezium/kafka:2.4
    container_name: kafka
    ports:
      - "9092:9092"
    environment:
      - ZOOKEEPER_CONNECT=zookeeper:2181
    depends_on:
      - zookeeper

  connect:
    image: quay.io/debezium/connect:2.4
    container_name: connect
    ports:
      - "8083:8083"
    environment:
      - BOOTSTRAP_SERVERS=kafka:9092
      - GROUP_ID=1
      - CONFIG_STORAGE_TOPIC=my_connect_configs
      - OFFSET_STORAGE_TOPIC=my_connect_offsets
      - STATUS_STORAGE_TOPIC=my_connect_statuses
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      - kafka

```

### 2.2 启动环境

```bash
docker-compose up -d

```

---

## 3. 注册 Debezium 连接器 (触发同步)

创建 `register-connector.sh`，定义需要监听的数据库表和字段。

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
    "column.include.list": "public.payload.(id,title,content,category)"
  }
}'

```

---

## 4. Go 消费者同步逻辑 (应用层)

每个地区的边缘节点运行该程序，监听 Kafka 并更新本地 Meilisearch。

### 4.1 数据结构定义

```go
package main

import (
    "encoding/json"
    "github.com/meilisearch/meilisearch-go"
)

// Debezium 消息 payload 结构
type CDCEvent struct {
    Payload struct {
        Before map[string]interface{} `json:"before"`
        After  map[string]interface{} `json:"after"`
        Op     string                 `json:"op"` // c=create, u=update, d=delete
    } `json:"payload"`
}

```

### 4.2 核心处理逻辑

```go
func processMessage(msg []byte, meili *meilisearch.Client) {
    var event CDCEvent
    json.Unmarshal(msg, &event)

    index := meili.Index("payload")

    switch event.Payload.Op {
    case "c", "u": // 新增或修改
        documents := []map[string]interface{}{event.Payload.After}
        index.AddDocuments(documents)
    case "d": // 删除
        id := event.Payload.Before["id"].(string)
        index.DeleteDocument(id)
    }
}

```

---

## 5. 运维验证与监控

### 5.1 查看同步状态

```bash
# 查看 Connector 状态
curl -s localhost:8083/connectors/meili-connector/status

```

### 5.2 验证 Kafka 实时数据

```bash
docker exec -it kafka /kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic search_sync.public.payload \
  --from-beginning

```

### 5.3 故障处理

* **Connection Reset**: Kafka Connect 还在启动中，等待 30 秒再试。
* **400 Bad Request**: 检查数据库用户名、密码或 `wal_level` 是否配置正确。
* **Meilisearch 延迟**: 检查 Kafka 消费者的 `group_id` 是否冲突，或网络 RTT 延迟。

---

## 6. 架构优势总结

1. **高性能**：Meilisearch 在边缘节点提供 <50ms 的搜索体验。
2. **高可靠**：通过 WAL 日志捕获，保证数据库与搜索索引的最终一致性。
3. **低侵入**：业务代码无需修改，只需关注 PostgreSQL 写入即可。

