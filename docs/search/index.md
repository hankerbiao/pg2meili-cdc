# 搜索接口 (Search API)

本模块说明与搜索相关的 HTTP 接口，包括：

- UniData Search Service 的 `/search` 搜索接口；
- UniData Producer Service 提供的“索引（collection）管理”接口。

---

## 1. 索引管理接口（Producer）

索引管理接口由 UniData Producer Service 暴露，用于查询和删除某个应用在 UniData 中已写入过哪些集合（collection），便于前端或网关决定可用的业务索引。

### 1.1 获取当前应用下的索引列表

- **方法**：`GET`
- **路径**：`/api/v1/index/indexes`
- **说明**：返回当前 JWT 所属应用在 UniData 中已使用的 collection 名称列表。
- **鉴权方式**：`Authorization: Bearer <JWT>`

请求参数：

| 名称 | 位置 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `limit` | query | integer | 否 | 每次返回的最大条数，默认 `100`，最大 `500` |
| `offset` | query | integer | 否 | 起始偏移量，默认 `0` |

响应体：

- 类型：`string[]`
- 内容：去重后的 collection 名称数组，例如：

```json
[
  "requirements",
  "testcases",
  "bugs"
]
```

示例请求（curl）：

```bash
curl -X GET "http://localhost:8080/api/v1/data/indexes?limit=100" \
  -H "Authorization: Bearer <YOUR_JWT>"
```

### 1.2 删除索引（逻辑删除集合内所有文档）

- **方法**：`DELETE`
- **路径**：`/api/v1/index/indexes/{collection}`
- **说明**：删除当前应用下指定 collection 对应的索引，将该集合内所有文档的 `is_delete` 标记为 `true`。
- **鉴权方式**：`Authorization: Bearer <JWT>`

请求参数：

| 名称 | 位置 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `collection` | path | string | 是 | 要删除的集合名称，例如 `requirements`、`testcases` |

响应体示例：

```json
{
  "status": "success",
  "collection": "requirements",
  "deleted_count": 128
}
```

示例请求（curl）：

```bash
curl -X DELETE "http://localhost:8080/api/v1/data/indexes/requirements" \
  -H "Authorization: Bearer <YOUR_JWT>"
```

---

## 2. 搜索接口（Search Service）

本小节说明 UniData Search Service 暴露的 `/search` 接口，该接口直接对接 Meilisearch 搜索引擎。

### 2.1 接口概览

- **接口地址**：`POST /search`
- **基础域名**：
  - 天津环境：`http://10.17.154.252:8091`
  - 北京环境：`http://10.32.129.188:8091`
  - 本地示例：`http://localhost:8091`
- **协议**：HTTPS/HTTP
- **鉴权方式**：`Authorization: Bearer <JWT>`（应用级访问令牌）
- **数据格式**：`Content-Type: application/json`

### 2.2 公共请求头

- `Authorization`：必填，格式 `Bearer <JWT>`，用于标识调用方应用（`app_name`）
- `Content-Type`：必填，`application/json`

### 2.3 请求体参数

请求体为原样透传到 Meilisearch `POST /indexes/{index}/search` 的 JSON 对象，常用字段如下：

| 参数 | 类型 | 必填 | 说明 | 示例 |
| :--- | :--- | :--- | :--- | :--- |
| `q` | string | 是 | 搜索关键字 | `"电源"` |
| `offset` | integer | 否 | 起始偏移量，用于分页 | `0` |
| `limit` | integer | 否 | 返回条数 | `20` |
| `filter` | string/array | 否 | 过滤条件 | `tags = "BMC"` |
| `attributesToHighlight` | array | 否 | 需要高亮的字段列表 | `["*"]` |

说明：索引名称由后端根据 JWT 中的 `app_name` 和配置的基础索引名自动拼接，客户端无需在请求体中指定索引。

### 2.4 响应结果

接口返回 Meilisearch 原始搜索结果，主要字段包括：

- `hits`：文档数组，每个元素为一条命中的测试用例
- `hits[i].id`：用例内部 ID
- `hits[i].ext_id`：外部用例编号，例如 `BMC-114245`
- `hits[i].name`：用例名称
- `hits[i].summary`：用例摘要
- `hits[i].tags`：标签数组，例如 `["BMC issue", "AMD", "Intel"]`
- `hits[i]._formatted`：可选，高亮后的字段结果
  - `hits[i]._formatted.name`
  - `hits[i]._formatted.summary`

---

## 3. 搜索使用示例

### 3.1 简单关键字搜索

请求示例（curl）：

```bash
curl -X POST "http://localhost:8091/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源"
  }'
```

请求示例（JavaScript，fetch）：

```js
const BASE_URL = "http://localhost:8091";
const token = "<YOUR_JWT>";

async function searchSimple() {
  const resp = await fetch(`${BASE_URL}/search`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: "电源",
    }),
  });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }
  const data = await resp.json();
  console.log("hits:", data.hits);
}
```

### 3.2 高亮搜索

请求示例（curl）：

```bash
curl -X POST "http://localhost:8091/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "attributesToHighlight": ["*"]
  }'
```

请求示例（JavaScript，fetch）：

```js
async function searchWithHighlight() {
  const resp = await fetch(`${BASE_URL}/search`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: "电源",
      attributesToHighlight: ["*"],
    }),
  });
  const data = await resp.json();
  const hits = data.hits || [];
  if (hits.length > 0) {
    const doc = hits[0];
    console.log("name:", doc.name);
    console.log("summary:", doc.summary);
    if (doc._formatted) {
      console.log("highlighted name:", doc._formatted.name);
      console.log("highlighted summary:", doc._formatted.summary);
    }
  }
}
```

### 3.3 按标签过滤搜索

请求示例（curl）：

```bash
curl -X POST "http://localhost:8091/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "filter": ["tags = \"BMC\""]
  }'
```

请求示例（JavaScript，fetch）：

```js
async function searchFilterByTag() {
  const resp = await fetch(`${BASE_URL}/search`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: "电源",
      filter: ['tags = "BMC"'],
    }),
  });
  const data = await resp.json();
  console.log("hits:", data.hits);
}
```

### 3.4 分页搜索

请求示例（curl）：

```bash
curl -X POST "http://localhost:8091/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "offset": 0,
    "limit": 5
  }'
```

请求示例（JavaScript，fetch）：

```js
async function searchWithPagination(page = 1, pageSize = 5) {
  const offset = (page - 1) * pageSize;
  const resp = await fetch(`${BASE_URL}/search`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: "电源",
      offset,
      limit: pageSize,
    }),
  });
  const data = await resp.json();
  console.log(`page=${page} hits:`, data.hits);
}
```
