# APPS/MeliData curl 快速参考

内部联调用，覆盖从获取令牌到搜索成功的完整链路。需要 `curl` 和 `jq`。

先设置公共变量（有效期取一年后，macOS/Linux 通用；服务端允许的 Key 有效期上限默认 100 年）：

```bash
export BASE_URL="https://meilisearch.1oa.com.cn"
export CLIENT_ID="apps"
export OWNER_ITCODE="替换成真实负责人 itcode"
export APP_NAME="apps_curl_test_$(date +%s)"
export IDEMPOTENCY_KEY="apps-curl-$(date +%s)-$RANDOM"
export EXPIRES_AT="$(date -u -v+1Y '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d '+1 year' '+%Y-%m-%dT%H:%M:%SZ')"
read -r -s -p "client secret: " CLIENT_SECRET; echo
```

安全要求：不要把 `CLIENT_SECRET`、`ACCESS_TOKEN` 或返回的业务 `api_key` 写进命令、Markdown、截图或 Git。`APP_NAME` 与 `IDEMPOTENCY_KEY` 在同一次开通与幂等重放测试之间必须保持不变。

## 1. 获取 token

```bash
TOKEN_JSON=$(curl -sS -X POST "$BASE_URL/oauth1/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=$CLIENT_ID" \
  --data-urlencode "client_secret=$CLIENT_SECRET" \
  --data-urlencode "scope=open-platform:apps:write open-platform:collections:write")
export ACCESS_TOKEN=$(printf '%s' "$TOKEN_JSON" | jq -r .access_token)
export REFRESH_TOKEN=$(printf '%s' "$TOKEN_JSON" | jq -r .refresh_token)
printf '%s\n' "$TOKEN_JSON" | jq '{token_type, expires_in, refresh_expires_in, scope}'
```

期望：HTTP `200`，能得到 `ACCESS_TOKEN` 和 `REFRESH_TOKEN`。这是管理面令牌，只能调用 open-platform 管理接口，不能用于业务数据读写。

## 2. 刷新 token

```bash
TOKEN_JSON=$(curl -sS -X POST "$BASE_URL/oauth2/refresh" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=refresh_token" \
  --data-urlencode "client_id=$CLIENT_ID" \
  --data-urlencode "refresh_token=$REFRESH_TOKEN")
export ACCESS_TOKEN=$(printf '%s' "$TOKEN_JSON" | jq -r .access_token)
export REFRESH_TOKEN=$(printf '%s' "$TOKEN_JSON" | jq -r .refresh_token)
printf '%s\n' "$TOKEN_JSON" | jq '{token_type, expires_in, refresh_expires_in, scope}'
```

期望：HTTP `200`。旧 `REFRESH_TOKEN` 不能再次使用，再次使用应返回 HTTP `401`、`invalid_grant`。

## 3. 开通应用

```bash
BOOTSTRAP=$(curl -sS -X POST "$BASE_URL/api/v1/open-platform/apps/bootstrap" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"app_name\":\"$APP_NAME\",\"display_name\":\"curl test\",\"owner_itcode\":\"$OWNER_ITCODE\",\"initial_keys\":[{\"name\":\"curl-key\",\"scopes\":[\"data:write\",\"search:read\"],\"expires_at\":\"$EXPIRES_AT\"}]}")
printf '%s\n' "$BOOTSTRAP" | jq 'del(.data.keys[].api_key)'
export APP_ID=$(printf '%s' "$BOOTSTRAP" | jq -r .data.app.id)
export BUSINESS_API_KEY=$(printf '%s' "$BOOTSTRAP" | jq -r .data.keys[0].api_key)
```

期望首次 HTTP `201`；`APP_ID` 和一次性 `BUSINESS_API_KEY` 会写入当前 shell 变量。
同样的请求体和 `Idempotency-Key` 重放期望 HTTP `200`，重放响应中的 `api_key` 应为
`null`。不要因重放失败就更换幂等键，否则会创建新应用。

## 4. 更新集合配置

先设置已有测试应用和集合：

```bash
export APP_ID="替换成测试应用 ID"
export COLLECTION="替换成已有集合名"
```

```bash
curl -i -sS -X PATCH "$BASE_URL/api/v1/open-platform/apps/$APP_ID/collections/$COLLECTION/settings" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"filterableAttributes":["status"],"sortableAttributes":["updated_at"],"searchableAttributes":["title"],"displayedAttributes":["id","title","status"]}'
```

期望：HTTP `200`，响应为 `{ "data": ..., "message": "ok" }`。这表示中心配置已保存，
不代表区域节点已经同步完成。

## 5. 写入文档

使用第 3 步返回的业务 Key（需要 `data:write` scope）。单条写入：

```bash
curl --fail-with-body -sS -X POST "$BASE_URL/api/v1/data/demo_collection" \
  -H "Authorization: Bearer $BUSINESS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id":"demo-001","name":"demo keyboard","status":"active"}'
```

期望：HTTP `201`，响应为 `{"data":{"id":"demo-001","collection":"demo_collection"},"message":"ok"}`。
重复提交同一 `id` 是幂等覆盖，可安全重试。

批量写入（单次最多 1000 条、请求体不超过 5 MiB、请求内 id 不得重复）：

```bash
curl --fail-with-body -sS -X POST "$BASE_URL/api/v1/data/demo_collection/batch" \
  -H "Authorization: Bearer $BUSINESS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"id":"demo-002","name":"demo mouse"},{"id":"demo-003","name":"demo hub"}]}'
```

期望：HTTP `201`，`data` 包含 `status`、`collection`、`count`、`ids`。

## 6. 区域搜索

使用同一业务 Key（需要 `search:read` scope）。线上公网搜索入口带 `/documents`
反向代理前缀；直连区域 Agent 内网地址时不要加该前缀：

```bash
curl --fail-with-body -sS -X POST "$BASE_URL/documents/api/v1/collections/demo_collection/search" \
  -H "Authorization: Bearer $BUSINESS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"q":"demo","limit":10}'
```

期望：HTTP `200`，响应固定为 `{data, meta, error}`，业务结果在 `data.hits`，
`meta.request_id` 用于排障。

搜索为空不代表写入失败：写入经 CDC 异步传播到区域节点，等几秒重试即可；单区域场景
固定使用上面的入口即可，多区域场景才需要先调 `GET /api/v1/agents/online` 发现节点。

## 已知问题

- 第 3 步（开通应用）幂等重放在线上可能返回 HTTP `500`：本地已修复响应序列化，但尚未
  部署时线上重放仍会失败。首次开通返回 `201` 不受影响；重放失败时不要更换幂等键
  再次创建，以免产生额外应用，等待修复部署后重试即可。
