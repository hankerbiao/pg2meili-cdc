# 从申请 Key 到搜索成功

从创建应用到区域搜索只有四步。先看流程，再按下方步骤完成接入；完整请求路径、参数和响应示例见 API Reference。

## 接入流程一览

| 顺序 | 环节 | 负责人 | 说明 |
| --- | --- | --- | --- |
| 01 | 开通应用与 API Key | 开通人 | 创建应用、选择所需 scope，并安全交付 API Key。 |
| 02 | 服务端写入数据 | 业务开发者 | 调用 `POST /api/v1/data/{collection}`，使用 `data:write`。 |
| 03 | CDC 自动同步 | 平台自动 | PostgreSQL → Outbox → Debezium → Kafka → 区域 Agent → Meilisearch。 |
| 04 | 通过区域 Agent 搜索 | 业务开发者 | 调用搜索端点，使用 `search:read`；写入后需等待异步同步。 |

**推荐顺序：** 开通与交付 Key → 服务端写入 → 等待 CDC 同步 → 通过区域 Agent 搜索。

## 按顺序完成接入

### 01 了解什么是 MeliData 服务

MeliData 是面向应用的统一数据与搜索服务：业务数据通过数据 API 写入，再由区域 Agent 同步到 Meilisearch，提供就近、低延迟的搜索能力。

### 02 评估与 App 的搜索需求契合度

梳理需要搜索的集合、文档字段、过滤与排序条件，以及数据更新频率。确认你的场景适合全文检索和异步同步后，再进入接入流程。

### 03 开通应用并创建 API Key

由开通人在控制台创建应用，按实际用途申请最小权限范围，并为开发、测试、生产环境分别创建 API Key。密钥只在创建时展示一次，请立即保存到密钥管理系统再交付，不要通过截图或聊天记录传递。

### 04 交给 AI 页面网址学习

将当前页面网址或 AI Agent 集成指南的网址交给你的 AI 编程助手，让它学习服务边界、鉴权要求和代码示例，再开始生成接入方案。

### 05 开发代码

让 AI 先生成代码，再由你确认请求路径、集合名称、字段映射和错误重试策略。使用服务端环境变量保存配置，不要把密钥写入前端源码。

### 06 部署时填写 API Key

部署应用时，通过平台的 Secret 或环境变量注入 API Key，例如 `MELIDATA_API_KEY`。上线前按快速开始验证完整链路：写入一条文档，等待区域同步完成，搜索能命中该文档，再接入全量数据。

## 准备开始了吗？

把首页网址交给 AI，或直接从快速开始页面复制第一段请求示例。首页也可以直接分享给 AI 编程助手作为参考资料。

- 快速开始：`/open-platform/docs/quickstart`
- AI Agent 指南：`/open-platform/docs/agent-guide`
- API Reference：`/open-platform/docs/api-reference`
- 认证规则：`/open-platform/docs/authentication`

## 接口地址、认证与使用场景

以下地址为当前线上入口。数据写入和管理请求发送到 MeliData；搜索请求发送到区域 Agent。示例使用 `curl`，可在 macOS、Linux 或 Windows 的 WSL 中运行。

### 准备环境变量

在 MeliData 控制台创建应用和 API Key。按实际操作申请最小 scope：写入使用 `data:write`，读取使用 `data:read`，区域搜索使用 `search:read`。将 Key 放在业务服务的 Secret 或环境变量中，不要写进浏览器代码、代码仓库或客户端 App。

```bash
export MELIDATA_API_BASE_URL="https://meilisearch.1oa.com.cn/api/v1"
export MELIDATA_SEARCH_BASE_URL="https://meilisearch.1oa.com.cn/documents/api/v1"
export MELIDATA_API_KEY="替换为控制台创建的 API Key"
export COLLECTION="products"
```

所有数据 API 请求都使用以下认证头：

```http
Authorization: Bearer $MELIDATA_API_KEY
Content-Type: application/json
```

### 接口速查：什么场景调用什么接口

| 场景 | 方法与完整地址 | 所需 scope |
| --- | --- | --- |
| 新建或更新一条文档 | `POST https://meilisearch.1oa.com.cn/api/v1/data/{collection}` | `data:write` |
| 批量导入或更新文档 | `POST https://meilisearch.1oa.com.cn/api/v1/data/{collection}/batch` | `data:write` |
| 按 ID 读取文档 | `GET https://meilisearch.1oa.com.cn/api/v1/data/{collection}/{id}` | `data:read` |
| 分页读取集合文档 | `GET https://meilisearch.1oa.com.cn/api/v1/data/{collection}?limit=20&offset=0` | `data:read` |
| 软删除一条文档 | `DELETE https://meilisearch.1oa.com.cn/api/v1/data/{collection}/{id}` | `data:write` |
| 设置过滤和排序字段 | `POST https://meilisearch.1oa.com.cn/api/v1/indexes/{collection}/settings` | `data:write` |
| 在默认区域搜索 | `POST https://meilisearch.1oa.com.cn/documents/api/v1/collections/{collection}/search` | `search:read` |
| 查询可用区域 Agent | `GET https://meilisearch.1oa.com.cn/api/v1/agents/online` | `search:read` |

`{collection}` 是集合名称，例如 `products`、`articles`；`{id}` 是业务系统为文档分配的唯一 ID。接口地址中的花括号需要替换为实际值。

## 接口调用示例

### 1. 商品、文章或知识条目有新增或变更时：写入单条文档

使用 `POST /data/{collection}` 新建文档；如果同一 `id` 已存在，这个接口会更新该文档，适合业务事件触发的实时写入。

```bash
curl --fail-with-body -sS -X POST "$MELIDATA_API_BASE_URL/data/$COLLECTION" \
  -H "Authorization: Bearer $MELIDATA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "sku-001",
    "name": "Mechanical Keyboard",
    "category": "keyboard",
    "price": 699,
    "status": "available"
  }'
```

完整请求地址示例：`https://meilisearch.1oa.com.cn/api/v1/data/products`。

成功时通常返回 HTTP `201`，业务数据位于响应的 `data` 字段。每条文档必须包含稳定且唯一的 `id`；建议保留业务系统的主键作为 ID，便于更新、读取和删除。

### 2. 首次导入或定时同步大量数据时：批量写入

调用 `POST /data/{collection}/batch`，每个 `items` 元素都是一条文档。适合初始化商品目录、知识库、FAQ 或定时全量/增量同步。

```bash
curl --fail-with-body -sS -X POST "$MELIDATA_API_BASE_URL/data/$COLLECTION/batch" \
  -H "Authorization: Bearer $MELIDATA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"id": "sku-001", "name": "Mechanical Keyboard", "category": "keyboard", "price": 699},
      {"id": "sku-002", "name": "Wireless Mouse", "category": "mouse", "price": 199}
    ]
  }'
```

完整请求地址示例：`https://meilisearch.1oa.com.cn/api/v1/data/products/batch`。单次批量最多 1000 条，请求体不超过 5 MiB；同一批次中的 `id` 不能重复。较大的数据集请拆分成多个批次。

### 3. 业务后台需要查看某条原始数据时：读取文档

```bash
curl --fail-with-body -sS \
  "$MELIDATA_API_BASE_URL/data/$COLLECTION/sku-001" \
  -H "Authorization: Bearer $MELIDATA_API_KEY"
```

完整请求地址示例：`https://meilisearch.1oa.com.cn/api/v1/data/products/sku-001`。读取集合列表时使用 `GET /data/{collection}?limit=20&offset=0`；`limit` 范围为 1–100，`offset` 从 0 开始。文档 API 用于检查主数据，不用于面向终端用户的全文搜索。

### 4. 商品下架或内容删除时：软删除文档

```bash
curl --fail-with-body -sS -X DELETE \
  "$MELIDATA_API_BASE_URL/data/$COLLECTION/sku-001" \
  -H "Authorization: Bearer $MELIDATA_API_KEY"
```

完整请求地址示例：`https://meilisearch.1oa.com.cn/api/v1/data/products/sku-001`。删除是软删除，变更会进入 CDC 同步链路，并由区域索引移除对应文档。删除和写入一样需要 `data:write`。

### 5. 需要筛选或排序时：配置集合字段

只有当搜索需要按字段筛选或排序时才配置。下面示例允许按 `category`、`status` 过滤，并按 `price` 排序：

```bash
curl --fail-with-body -sS -X POST \
  "$MELIDATA_API_BASE_URL/indexes/$COLLECTION/settings" \
  -H "Authorization: Bearer $MELIDATA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "filterableAttributes": ["category", "status"],
    "sortableAttributes": ["price"]
  }'
```

完整请求地址示例：`https://meilisearch.1oa.com.cn/api/v1/indexes/products/settings`。字段名应与文档中的属性一致。设置通过 CDC 命令同步到区域索引，收到成功响应表示中心配置已保存；首次配置或修改后，等待区域处理完成再依赖新设置进行查询。

### 6. 面向用户展示搜索结果时：调用区域搜索

默认天津区域的公网入口如下。搜索 API 使用带 `/documents` 前缀的 Agent 地址：

```bash
curl --fail-with-body -sS -X POST \
  "$MELIDATA_SEARCH_BASE_URL/collections/$COLLECTION/search" \
  -H "Authorization: Bearer $MELIDATA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "q": "mechanical keyboard",
    "limit": 10
  }'
```

完整请求地址示例：`https://meilisearch.1oa.com.cn/documents/api/v1/collections/products/search`。结果列表位于响应的 `data.hits` 中。多区域部署时，应使用用户附近的区域 Agent 地址；也可先调用 `GET https://meilisearch.1oa.com.cn/api/v1/agents/online` 获取在线节点及区域信息，再按业务的区域路由策略选择搜索地址。单区域接入直接使用默认搜索地址即可。

## 推荐使用场景

- **商品目录搜索：** 将商品名称、品牌、类目、描述等写入 `products` 集合；按需配置类目筛选和价格排序，再从区域 Agent 提供商品搜索。
- **帮助中心与 FAQ：** 将标题、正文、产品线、语言和可见状态写入 `articles` 或 `faqs` 集合；内容发布或修改后调用写入接口，用户通过区域搜索获取相关条目。
- **内部制度、手册与知识库：** 将可检索的段落或文档条目写入集合，并携带部门、文档类型、发布日期等业务字段；按访问权限设计独立集合或由调用方完成结果权限校验。
- **工单、缺陷与项目记录：** 将需要快速查找的标题、描述、编号、状态和负责人写入集合；使用过滤字段配置支持状态或项目筛选。
- **多区域产品：** 中心业务服务负责写入，用户请求交给就近 Agent 搜索，减少跨区域搜索延迟。

MeliData 更适合需要全文检索、关键词查找和简单过滤/排序的文档型数据。订单结算、库存扣减等需要强事务一致性的操作仍应由业务数据库负责；搜索索引通过 CDC 异步更新，写入成功后搜索结果不会保证立即可见。建议先用少量样例验证字段、权限和搜索效果，再批量导入数据。

## 接入建议

1. 按业务边界选择集合，例如 `products`、`faqs`、`tickets`；字段尽量保持稳定，并为每条文档指定稳定的 `id`。
2. 为写入、读取和搜索分别评估所需 scope，创建独立环境的 Key；遵循最小权限原则，并定期轮换。
3. Key 只放在服务端 Secret 管理中。浏览器和移动端不要直接持有业务 API Key；应由自己的后端代为调用。
4. 事件驱动的单条写入适合实时更新；批量接口适合初始化、导入和周期同步。对 `429` 或临时 `5xx` 使用有限次数的退避重试。
5. 搜索是最终一致的。上线前验证“写入 → 等待区域同步 → 搜索命中”完整链路；如需确认索引进度，请查看控制台或联系平台管理员。
6. 过滤和排序只对已配置的字段开放。搜索接口的 `filter`、`sort` 等参数请按 API Reference 中该版本的定义使用。

## 线上 API 文档

- API Reference：<https://meilisearch.1oa.com.cn/open-platform/docs/api-reference>
- AI Agent 集成指南：<https://meilisearch.1oa.com.cn/open-platform/docs/agent-guide>
- 快速开始：<https://meilisearch.1oa.com.cn/open-platform/docs/quickstart>
- OpenAPI JSON：<https://meilisearch.1oa.com.cn/openapi.json>
