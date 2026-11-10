# APPS 与 MeliData 服务端集成

APPS 通过两条独立的凭证体系接入 MeliData：

- **管理面令牌**：APPS 以服务身份（OAuth client credentials）获取，只能调用 open-platform
  管理接口，用于自动开通应用、创建业务 Key 和配置集合。
- **业务 API Key**：由开通流程返回，交给 APP 后端做业务数据写入和区域搜索。

两套凭证不能互相替代：管理面令牌不能读写业务数据，业务 Key 不能管理应用。

完整联调命令见 [apps-melidata-curl-quick-reference.md](apps-melidata-curl-quick-reference.md)，
按 token → 开通 → 配置 → 写入 → 搜索的顺序可直接执行。

## 认证：获取管理面令牌

```http
POST /oauth1/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=apps&
client_secret=...&
scope=open-platform%3Aapps%3Awrite%20open-platform%3Acollections%3Awrite
```

成功响应包含短期 `access_token`、`expires_in`、一次性轮换 `refresh_token` 和
`refresh_expires_in`。管理请求使用：

```http
Authorization: Bearer <access_token>
```

刷新令牌只能使用一次：

```http
POST /oauth2/refresh
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
client_id=apps&
refresh_token=...
```

服务密钥和 JWT 签名密钥必须通过环境变量或 secret file 注入。生产环境还必须配置
`OPEN_PLATFORM_CREDENTIAL_ENCRYPTION_KEY_FILE`，用于加密托管业务 API Key。

## 自动开通应用

```http
POST /api/v1/open-platform/apps/bootstrap
Authorization: Bearer <access_token>
Idempotency-Key: <stable-operation-id>
Content-Type: application/json
```

请求体示例（`initial_keys` 可提交一个或两个初始业务 Key，`expires_at` 必须在未来且
不超过服务端允许的 Key 有效期上限，默认 100 年）：

```json
{
  "app_name": "apps_demo_001",
  "display_name": "演示应用",
  "owner_itcode": "zhangsan",
  "description": "由 APPS 自动开通",
  "initial_keys": [
    {
      "name": "default",
      "scopes": ["data:write", "search:read"],
      "expires_at": "2027-11-02T00:00:00Z"
    }
  ]
}
```

幂等规则：相同 `client_id` 与 `Idempotency-Key` 的相同请求只创建一次；请求体不同会
返回 `409 IDEMPOTENCY_KEY_REUSED`。

首次成功响应（HTTP `201`）返回业务 Key 明文和 `credential_ref`。明文只在首次响应中
返回，APPS 应立即保存到自己的密钥系统。幂等重试（HTTP `200`）只返回应用和 Key 元数据，
`api_key` 为空；如果 APPS 在首次响应后丢失明文，进入受控人工恢复或撤销流程。

## 配置集合设置

```http
PATCH /api/v1/open-platform/apps/{app_id}/collections/{collection}/settings
Authorization: Bearer <access_token>
Content-Type: application/json
```

服务调用必须完整提交以下字段，空数组表示清空：

```json
{
  "filterableAttributes": ["project_id", "status"],
  "sortableAttributes": ["updated_at"],
  "searchableAttributes": ["title", "description"],
  "displayedAttributes": ["id", "title", "project_id", "status", "updated_at"]
}
```

成功表示中心期望态已保存，不表示所有区域已经完成同步。

## 运行时调用：业务数据面

APP 后端使用 bootstrap 返回的业务 Key（`Authorization: Bearer <业务 Key>`）：

- `POST /api/v1/data/{collection}`（单条写入）需要 `data:write`。
- `POST /api/v1/data/{collection}/batch` 需要 `data:write`。
- `DELETE /api/v1/data/{collection}/{id}` 需要 `data:write`。
- `GET /api/v1/agents/online?region=<region>` 需要 `search:read`。
- 区域搜索：`POST {搜索入口}/api/v1/collections/{collection}/search`，请求体使用
  `q`、`limit`、`offset`、`filter`、`sort`。

区域搜索返回 `{data, meta, error}`。业务结果位于 `data.hits` 和
`data.estimatedTotalHits`；`meta.request_id` 用于排障。写入通过 CDC、outbox、Kafka 和
区域 Agent 异步传播，空结果不能直接解释为写入失败。

### 搜索入口怎么选

- **单区域（当前默认）**：直接使用固定公网入口
  `https://meilisearch.1oa.com.cn/documents`。`/documents` 是反向代理前缀，不是
  Agent 内部路由的一部分，直连内网 Agent 时不加。
- **多区域**：先调 `GET /api/v1/agents/online?region=<区域>` 获取在线节点，再向返回的
  `base_url` 发起搜索。节点列表是短期运行时发现结果，APP 应缓存几秒并在连接失败后
  重新发现，不应永久持久化为静态配置。发现接口本身只需要 `search:read`。

### 批量写入

请求体为 `{ "items": [{ "id": "...", "...": "..." }] }`。单次请求最多 1000 个文档，
请求体上限为 5 MiB；每个请求内 `id` 不得重复。数据库使用
`(app_id, collection, id)` upsert，因此重复提交同一文档是幂等的。一次请求在数据库层
整体提交，失败返回 5xx 时不要把响应解释为部分成功；客户端应使用同一文档集合重试。
成功响应（HTTP `201`）为 `{data: {status, collection, count, ids}, message}`。

### 删除文档

`DELETE /api/v1/data/{collection}/{id}` 只做软删除并产生异步索引删除事件。文档不存在或
已经删除时返回 `404`，不会伪造成功；成功响应仍使用中心 API 的 `{data, message}` 包装。

### 区域搜索参数与错误处理

collection 只能包含字母、数字、下划线和连字符，长度 1-128。请求体必须是 JSON 对象，
最大 1 MiB；兼容 `query`/`highlight` 别名，会规范化为 `q`/`attributesToHighlight`。
`limit` 可选，必须是 1-1000 的整数；`offset`、`filter`、`sort` 按 Meilisearch 搜索参数
传递。响应最大 16 MiB。

所有区域搜索响应固定为：

```json
{
  "data": {"hits": [], "estimatedTotalHits": 0},
  "meta": {"request_id": "req_...", "region": "beijing", "duration_ms": 12},
  "error": null
}
```

错误码包括 `INVALID_AUTHORIZATION`、`INVALID_API_KEY`、`INSUFFICIENT_SCOPE`、
`INVALID_COLLECTION`、`INVALID_JSON`、`INVALID_LIMIT`、`SEARCH_INDEX_NOT_FOUND`、
`SEARCH_RATE_LIMITED` 和 `SEARCH_BACKEND_UNAVAILABLE`。

重试规则：`401`、`403`、`404`、`422` 应停止并修正请求；`429`、`5xx`、网络错误带
`error.retryable=true` 时按有界退避重试。

## 限制速查

| 项目 | 限制 |
| --- | --- |
| 批量写入条数 | 单次最多 1000 条 |
| 批量写入请求体 | 不超过 5 MiB，请求内 `id` 不得重复 |
| 文档 `id` | 非空字符串，同一文档按 `id` 幂等覆盖 |
| 集合名称 | 1-128 位，仅字母、数字、下划线、连字符，以字母或数字开头 |
| 搜索请求体 | 不超过 1 MiB，`limit` 取值 1-1000 |
| 搜索响应 | 不超过 16 MiB |
| 业务 Key 有效期 | 上限默认 100 年，到期前轮换 |
| 在线节点缓存 | 建议缓存几秒，连接失败后重新发现 |

## 联调

按顺序手工执行全部步骤（token → 刷新 → 开通 → 集合配置 → 写入 → 搜索）的 curl
命令与期望响应，见 [apps-melidata-curl-quick-reference.md](apps-melidata-curl-quick-reference.md)。

注意：M01 创建的应用没有删除入口，联调请使用测试应用与测试集合；不要在命令、终端
录屏或工单中公开客户端密钥、token 或返回的业务 API Key。
