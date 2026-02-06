# 搜索接口 (Search API)

本模块说明与搜索相关的 HTTP 接口，包括：

- UniData Search Service 的 `/search` 搜索接口；
- 索引管理请参考「数据管理」文档：`/management/index`。
- 代理节点在线列表接口。

---
## 1. 搜索接口（Search Service）

本小节说明 UniData Search Service 暴露的 `/search` 接口，该接口直接对接 Meilisearch 搜索引擎。

### 1.1 接口概览

- **接口地址**：`POST /search?collection={collection}`
- **基础域名**：
  - 天津环境：`http://10.17.154.252:8091`
  - 北京环境：`http://10.32.129.188:8091`
  - 本地示例：`http://localhost:8091`
- **协议**：HTTPS/HTTP
- **鉴权方式**：`Authorization: Bearer <JWT>`（应用级访问令牌）
- **数据格式**：`Content-Type: application/json`

### 1.2 公共请求头

- `Authorization`：必填，格式 `Bearer <JWT>`，用于标识调用方应用（`app_name`）
- `Content-Type`：必填，`application/json`

### 1.3 请求体参数

请求体为原样透传到 Meilisearch `POST /indexes/{index}/search` 的 JSON 对象，常用字段如下：

| 参数 | 类型 | 必填 | 说明 | 示例 |
| :--- | :--- | :--- | :--- | :--- |
| `q` | string | 是 | 搜索关键字 | `"电源"` |
| `offset` | integer | 否 | 起始偏移量，用于分页 | `0` |
| `limit` | integer | 否 | 返回条数 | `20` |
| `filter` | string/array | 否 | 过滤条件 | `tags = "BMC"` |
| `attributesToHighlight` | array | 否 | 需要高亮的字段列表 | `["*"]` |
| `attributesToRetrieve` | array | 否 | 指定返回字段白名单 | `["id", "name", "summary"]` |

### 1.4 查询参数

| 参数 | 位置 | 类型 | 必填 | 说明 | 示例 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `collection` | query | string | 是 | 集合名称，用于定位索引 | `testcases` |

### 1.5 代理行为说明

说明：

- `collection` 为必填查询参数，用于指定集合名称。
- 真实索引名由后端按 `indexUID = <app_name>_<collection>` 规则拼接。
- 请求体会透传给 Meilisearch，但服务端会自动补充 `showRankingScore: true`（如未显式提供）。

### 1.6 索引命名与设置说明

- **索引命名规则**：`<app_name>_<collection>`。
- **索引设置能力**：当前搜索服务为代理模式，不提供索引配置接口（如 searchable/filterable/sortable 等设置由后端统一配置）。

### 1.7 响应结果

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

## 2. 代理节点在线列表

该接口由 UniData 提供，用于获取当前在线的代理节点 IP 列表。

- **接口地址**：`GET /api/v1/agents/online`
- **基础地址（示例）**：`http://localhost:8080`
- **鉴权方式**：`Authorization: Bearer <YOUR_JWT>`

**请求示例**：

```bash
curl -X GET "http://localhost:8080/api/v1/agents/online" \
  -H "Authorization: Bearer <YOUR_JWT>"
```

**返回示例**：

```json
[
  { "ip": "10.17.154.252", "port": 8091, "hostname": "edge-tj-01" },
  { "ip": "10.32.129.188", "port": 8091, "hostname": "edge-bj-01" }
]
```

---

## 3. 搜索使用示例

### 3.1 简单关键字搜索

请求示例：

::: code-group

```bash [curl]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源"
  }'
```

```js [JavaScript]
const BASE_URL = "http://localhost:8091";
const token = "<YOUR_JWT>";

async function searchSimple() {
  const resp = await fetch(`${BASE_URL}/search?collection=testcases`, {
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

:::

### 3.2 高亮搜索

请求示例：

::: code-group

```bash [curl]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "attributesToHighlight": ["*"]
  }'
```

```bash [curl (自定义高亮标签)]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "attributesToHighlight": ["*"],
    "highlightPreTag": "<mark class=\"hit\">",
    "highlightPostTag": "</mark>"
  }'
```

```js [JavaScript]
async function searchWithHighlight() {
  const resp = await fetch(`${BASE_URL}/search?collection=testcases`, {
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

:::

### 3.3 按标签过滤搜索

请求示例：

::: code-group

```bash [curl]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "filter": ["tags = \"BMC\""]
  }'
```

```js [JavaScript]
async function searchFilterByTag() {
  const resp = await fetch(`${BASE_URL}/search?collection=testcases`, {
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

:::

### 3.4 分页搜索

请求示例：

::: code-group

```bash [curl]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "offset": 0,
    "limit": 5
  }'
```

```js [JavaScript]
async function searchWithPagination(page = 1, pageSize = 5) {
  const offset = (page - 1) * pageSize;
  const resp = await fetch(`${BASE_URL}/search?collection=testcases`, {
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

:::

### 3.5 排序搜索

请求示例：

::: code-group

```bash [curl]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "sort": ["updated_at:desc"]
  }'
```

```js [JavaScript]
async function searchWithSort() {
  const resp = await fetch(`${BASE_URL}/search?collection=testcases`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: "电源",
      sort: ["updated_at:desc"],
    }),
  });
  const data = await resp.json();
  console.log("hits:", data.hits);
}
```

:::

### 3.6 多条件过滤搜索

请求示例：

::: code-group

```bash [curl]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "filter": [
      "tags = \"BMC\"",
      "status = \"open\""
    ]
  }'
```

```js [JavaScript]
async function searchWithMultiFilter() {
  const resp = await fetch(`${BASE_URL}/search?collection=testcases`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: "电源",
      filter: ['tags = "BMC"', 'status = "open"'],
    }),
  });
  const data = await resp.json();
  console.log("hits:", data.hits);
}
```

:::

### 3.7 返回字段与摘要裁剪

请求示例：

::: code-group

```bash [curl]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "attributesToRetrieve": ["id", "name", "summary", "tags"],
    "attributesToCrop": ["summary"],
    "cropLength": 60
  }'
```

```js [JavaScript]
async function searchWithRetrieveAndCrop() {
  const resp = await fetch(`${BASE_URL}/search?collection=testcases`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: "电源",
      attributesToRetrieve: ["id", "name", "summary", "tags"],
      attributesToCrop: ["summary"],
      cropLength: 60,
    }),
  });
  const data = await resp.json();
  console.log("hits:", data.hits);
}
```

:::

### 3.8 精准搜索（双引号关键字）

说明：精准搜索可将关键字用双引号包裹，支持多个关键字同时匹配。

差异说明：

- **普通搜索**：分词/模糊匹配，召回更广，适合探索性检索。
- **精准搜索**：双引号内的词作为整体匹配，召回更窄，适合确认具体术语或短语。

请求示例：

::: code-group

```bash [curl]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "\"电源\" \"告警\""
  }'
```

```js [JavaScript]
async function searchExact() {
  const resp = await fetch(`${BASE_URL}/search?collection=testcases`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: "\"电源\" \"告警\"",
    }),
  });
  const data = await resp.json();
  console.log("hits:", data.hits);
}
```

:::

### 3.9 分面统计（Facets）

分面统计用于对搜索结果做分类统计，常见于“状态/标签”等筛选项。
例如在搜索结果中统计 `status` 或 `tags` 的数量分布，便于前端展示筛选列表。

请求示例：

::: code-group

```bash [curl]
curl -X POST "http://localhost:8091/search?collection=testcases" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  --data-raw '{
    "q": "电源",
    "facets": ["tags", "status"]
  }'
```

```js [JavaScript]
async function searchWithFacets() {
  const resp = await fetch(`${BASE_URL}/search?collection=testcases`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: "电源",
      facets: ["tags", "status"],
    }),
  });
  const data = await resp.json();
  console.log("facetDistribution:", data.facetDistribution);
}
```

:::
