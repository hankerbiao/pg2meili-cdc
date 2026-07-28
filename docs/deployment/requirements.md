# 系统需求

在开始部署 UniData 分布式系统之前，请确保您的环境满足以下硬件和软件要求。作为生产级分布式系统，建议预留充足的计算与存储资源以保证高可用性与高性能。

## 硬件要求

| 组件 | 最低配置 (生产环境) | 推荐配置 (高性能) | 说明 |
| :--- | :--- | :--- | :--- |
| **应用服务器** | 4 Core, 8GB RAM | 8 Core, 16GB RAM | 运行 UniData API 和 Sync Service，确保高并发处理能力 |
| **数据库服务器** | 8 Core, 16GB RAM | 16 Core, 64GB RAM | 运行 PostgreSQL，大内存可显著提升缓存命中率与查询性能 |
| **消息队列/搜索** | 8 Core, 16GB RAM | 16 Core, 64GB RAM | 运行 Kafka 和 Meilisearch，内存密集型组件，建议使用 SSD 存储 |

> **注意**: 上述配置为单一节点的建议资源。对于异地多活架构，建议在各区域独立部署消息队列与搜索节点，以实现最佳的访问延迟。

## 软件依赖

### 基础环境
- **操作系统**: Linux (推荐 Enterprise Linux 7+, Ubuntu 20.04+ 或 Debian 11+)
- **Docker**: 20.10+ (用于运行基础组件)
- **Docker Compose**: 2.0+

### 核心服务依赖
如果您选择通过源码部署核心服务，需要安装以下环境：

#### UniData (Python 服务)
- **Python**: >= 3.11
- **包管理器**: 推荐 [uv](https://github.com/astral-sh/uv) 或 pip

#### Sync Service (Go 服务)
- **Go**: >= 1.25.4 (如果需要从源码编译)
- **运行环境**: Linux 二进制文件 (glibc 2.17+)

### 存储与中间件
以下组件通常通过 Docker 部署，但也支持独立安装：

- **PostgreSQL**: 14+ 
  - 必须开启 `wal_level = logical` 以支持 CDC。
- **Kafka**: 3.0+
- **Meilisearch**: v1.8+
- **Redis**: 6.0+ (用于 Token 撤销缓存)

## 网络要求

- **端口开放**: 确保各组件之间的端口通信正常（如 5432, 9092, 7700, 8080 等）。
- **网络延迟**: 在异地多活部署场景下，Sync Service 与中心 Kafka 之间的网络稳定性对同步延迟有直接影响。
