# 运行和维护介绍

本章节涵盖服务的日常操作、Token 管理及故障排查指南。

## 服务管理

### 启动与停止

**UniData (Python)**
```bash
# 启动
uvicorn app.main:app --host 0.0.0.0 --port 8080

# 停止
# Ctrl+C 或 kill 进程
```

**Sync Service (Go)**
```bash
# 启动
./sync-service

# 停止
# Ctrl+C 或 kill 进程
```

**Docker 组件**
```bash
# 启动
docker-compose up -d

# 停止
docker-compose down

# 查看日志
docker-compose logs -f [service_name]
```

### 健康检查

**UniData**
```bash
curl http://localhost:8080/health
# 返回: {"status": "healthy"}
```

**Debezium Connector**
```bash
# 查看 Connector 状态
curl -s localhost:8083/connectors/meili-connector/status
```

## Token 管理

### 生成 Token

使用 `UniData/scripts/generate_jwt.py` 脚本生成 JWT Token。

```bash
cd UniData

# 生成 app 为 myapp，默认长期有效的 token
python scripts/generate_jwt.py --app-name myapp

# 指定 scopes 和有效期（1 天）
python scripts/generate_jwt.py \
  --app-name myapp \
  --scopes testcases:read,indexes:read \
  --ttl 86400
```

### Token 撤销与同步

系统采用“撤销事件广播 + 本地内存缓存 + Redis 缓存”的机制处理 Token 撤销。

1. **撤销广播**: UniData 在撤销 token 时向 Kafka (`token.revocations`) 发送事件。
2. **本地缓存**: 各地 Sync Service 消费事件，写入本地内存和 Redis。
3. **校验**: 接口验签时会检查 `jti` 是否在撤销列表中。

**维护注意**:
- 确保各区域部署本地 Redis，避免跨区访问延迟。
- Redis 异常时，系统会根据配置策略降级。

## 故障排查

### 常见问题

#### 1. Kafka 无法连接
- **现象**: Sync Service 或 Debezium 报错无法连接 Broker。
- **检查**: 检查 `KAFKA_BROKERS` 地址是否可达；检查 Docker 网络配置。

#### 2. Meilisearch 写入失败
- **现象**: 数据在 PG 更新但搜索搜不到。
- **检查**:
  - 检查 Debezium Connector 状态是否 `RUNNING`。
  - 检查 Sync Service 日志是否有报错。
  - 检查 `MEILI_HOST` 和 `MEILI_API_KEY` 配置。

#### 3. Token 验证失败
- **现象**: API 返回 401 Unauthorized。
- **检查**:
  - 确认 Token 是否过期。
  - 确认 `JWT_SECRET` 在 UniData 和 Sync Service 之间是否一致。
  - 确认 Token 是否已被撤销。
