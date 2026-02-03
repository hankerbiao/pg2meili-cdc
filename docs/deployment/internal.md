# 自研工具部署

本章节说明项目中自研的同步与管理工具的部署与使用。

## 1. Debezium 连接器注册 (Connector)

用于向 Kafka Connect 注册 PostgreSQL 监听任务。

### 1.1 注册脚本 (`register-connector.sh`)

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

### 1.2 运维命令

```bash
# 查看 Connector 状态
curl -s localhost:8083/connectors/meili-connector/status
```

## 2. 异地同步服务 (Go Consumer)

部署在各地区边缘节点的同步程序，负责消费 Kafka 消息并写入本地 Meilisearch。

### 2.1 部署流程

请使用实际服务代码进行部署与运行，入口见：

- `meilisearch-sync-service/main.go`

如需配置参数，请参考该服务的配置文件与环境变量说明。

### 2.2 核心逻辑示例（参考）

以下为逻辑示意，便于理解 CDC 消息处理流程（不代表完整可运行代码）。

```go
package main

import (
    "encoding/json"
    "github.com/meilisearch/meilisearch-go"
)

type CDCEvent struct {
    Payload struct {
        Before map[string]interface{} `json:"before"`
        After  map[string]interface{} `json:"after"`
        Op     string                 `json:"op"`
    } `json:"payload"`
}

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

### 2.2 故障排查

- **Kafka 无法连接**: 检查 `BOOTSTRAP_SERVERS` 地址是否可达。
- **Meilisearch 写入失败**: 检查 `MEILI_HOST` 和 `MEILI_API_KEY` 是否正确。
