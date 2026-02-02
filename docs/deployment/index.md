# 部署指南概览

UniData 的异地分布式部署涉及多个组件的协同工作。为了方便管理与维护，我们将部署流程分为 **开源基础组件** 与 **自研业务工具** 两大部分。

建议您按照以下顺序进行部署：

## 1. 部署开源基础组件

首先搭建数据存储与消息流转的基础设施。

- **[开源组件部署](/deployment/oss)**
  - PostgreSQL (数据源)
  - Kafka + Debezium (消息中间件)
  - Meilisearch (搜索引擎)

## 2. 部署自研业务工具

在基础设施就绪后，部署业务逻辑层以串联数据流。

- **[UniData 服务部署](/deployment/unidata)**
  - 写入入口与数据生产服务 (FastAPI)
- **[自研工具部署](/deployment/internal)**
  - Debezium Connector (同步触发器)
  - Go Sync Service (异地同步服务)

---

## 架构图示

```mermaid
graph LR
    User[Client] -->|HTTP| Uni[UniData]
    Uni -->|Write| PG[PostgreSQL]
    PG -->|CDC| Deb[Debezium]
    Deb -->|Msg| Kafka[Kafka]
    Kafka -->|Consume| Sync[Go Sync Service]
    Sync -->|Write| Meili[Meilisearch]
```
