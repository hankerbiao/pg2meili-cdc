# CDC 链路运维手册（重建 / 冷启动 / DLQ / 部署）

> 适用版本：2026-11-04 起，Debezium connector `snapshot.mode=never`（仅增量）。
> 背景：`always` 模式会在每次 connector 重启/重注册时把 `search_outbox` 全表重灌进
> Kafka（数百万条消息），已永久废弃。改为 `never` 后失去自动全量重灌这条"自愈路径"，
> 以下手册补齐人工兜底手段。

## 1. 全量重建某个 Meilisearch 索引

适用：索引数据损坏、需要重新映射字段、`snapshot.mode=never` 期间消费中断过久导致
索引与业务库不一致。

1. 确认 connector 当前为 `never`：
   ```bash
   curl -s localhost:8083/connectors/pg-search-outbox-connector/config | grep snapshot.mode
   ```
2. 删除目标索引（让 sync 走 `meili.commands` 重建，或直接调 Meilisearch API 删除）。
3. 触发业务库重新产出 outbox 事件：对目标 collection 的全量文档执行一次批量
   touch/重写（UniData 侧脚本），事件经 CDC → Kafka → sync 全量 upsert 到新索引。
4. 验证：`sync` 消费积压归零、索引文档数与业务库一致。

> 不推荐临时把 `snapshot.mode` 改回 `always` 重灌全表：outbox 表按保留策略清理后
> 已不含全量文档，重灌覆盖不了"表里没有但索引该有"的数据。

## 2. 冷启动（新消费者组 / 新区域 / offset 丢失）

- `ConsumeResetOffset(AtStart)` 只能回放 Kafka 保留期内的消息（outbox topic 已设
  30 天）。因此**消费中断超过 30 天 = 消息永久丢失**，只能走 §1 重建。
- offset 丢失（`__consumer_offsets` 损坏等）但保留期内：重置消费组到 earliest 即可
  回放（Meilisearch upsert/delete 幂等，重复消费无害）：
  ```bash
  docker exec pg2meili-kafka-1 /kafka/bin/kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --group meilisearch-sync-service-local --topic pg.public.search_outbox \
    --reset-offsets --to-earliest --execute
  ```

## 3. 复制槽 / connector 故障

- **PG 重启后 connector task 会 FAILED 且 Connect 不自动重试**（实测 2026-11-04）。
  恢复：
  ```bash
  curl -X POST 'http://localhost:8083/connectors/pg-search-outbox-connector/restart?includeTasks=true&onlyFailed=true'
  ```
  巡检脚本（每 5 分钟）已包含该检测与自动重启。
- 槽长期不活跃会导致 WAL 无限堆积（曾积到 27GB）。巡检覆盖：槽延迟 >500MB、
  pg_wal >5GB 告警，见 `logs/health_check.log`。

## 4. DLQ 处理

`meili.dlq` 保存永久失败的消息（完整原文 base64 + 错误原因）。巡检对 DLQ 深度 >100
告警。处理：

```bash
# 查看最早几条的错误原因
docker exec pg2meili-kafka-1 /kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic meili.dlq --from-beginning --max-messages 3 \
  | python3 -m json.tool
```

修复根因（如缺路由字段的数据、Meilisearch 校验规则变化）后，把 `value_base64` 解码
回原消息重投到 `source_topic` 对应分区即可回放；确认不再需要的消息用
`kafka-delete-records.sh` 截断。

## 5. 扩分区警告（当前保持 1 分区）

Debezium 以 outbox 表主键 `event_id` 作为消息 key。如果 `pg.public.search_outbox`
扩到多分区，同一文档的事件会被散到不同分区、并行消费时**文档级顺序被打散**
（upsert 晚于 delete 落库）。扩展前必须改为按 `document_id` 路由（需自定义 SMT 或
改造 outbox 表主键），否则不要动分区数。

## 6. sync 服务部署流程（服务器离线构建）

服务器 docker mirror 当前拉不到 `golang:1.25-alpine`（403），在线构建不可用；采用
与既有部署一致的离线流程：

```bash
# 1) 本地交叉编译（macOS → linux/amd64）
cd meilisearch-sync-service
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /tmp/mss ./main.go

# 2) 上传到服务器部署目录（含 Dockerfile.offline：FROM rollback 基础镜像 + COPY 二进制）
scp /tmp/mss melidata114:/data/pg2meili-cdc/backups/<deploy-dir>/meilisearch-sync-service

# 3) 服务器上构建镜像并重启（不触发在线构建）
docker build -t pg2meili-meilisearch-sync:<tag> -f Dockerfile.offline <deploy-dir>/
docker tag pg2meili-meilisearch-sync:<tag> pg2meili-meilisearch-sync:latest
cd /data/pg2meili-cdc && docker compose -p pg2meili up -d --no-build meilisearch-sync
```

注意：`docker compose up` 会因 env_file 内容变化**连带重建依赖容器**（postgres 等），
进而触发 §3 的 connector task FAILED——重启后留意巡检日志自动恢复。

## 7. 日常巡检与维护（cron）

| 项目 | 频率 | 脚本 | 日志 |
|---|---|---|---|
| 链路巡检（容器/健康接口/槽延迟/积压/DLQ/WAL/磁盘/负载） | 每 5 分钟 | `scripts/health_check.sh` | `logs/health_check.log` |
| outbox 表清理（保留 14 天，分批删除） | 每天 04:30 | `scripts/outbox_cleanup.sh 14` | `logs/outbox_cleanup.log` |

告警排查：`grep -E 'WARN|FAIL' logs/health_check.log`。
`outbox_cleanup` 必须以 postgres 超级用户执行（`search_outbox` 有 FORCE RLS，
业务角色看不到全表行）；删除产生的 `after=null` 事件由 sync 按 no-op 确认。
