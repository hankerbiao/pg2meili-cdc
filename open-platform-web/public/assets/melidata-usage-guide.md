# MeliData AI Agent 开发接入手册

本手册用于指导 AI 编程助手为业务应用集成 MeliData。它包含接入前需要确认的信息、接口选择方法、请求示例、上线建议和端到端验收流程。接口细节以线上 OpenAPI 定义和 API Reference 为准。

## Agent 的工作目标与边界

根据业务需求生成并集成服务端代码，使业务数据能够写入 MeliData，并经 CDC 同步到区域索引供搜索使用。

AI Agent 应遵守以下规则：

- 先收集本手册“接入前信息清单”中的信息；缺少关键字段时，列出需要用户确认的内容，不要编造字段、集合名或权限。
- 先查线上 API Reference 和 OpenAPI，再确定请求路径、字段、参数和响应处理方式。
- 只生成服务端调用代码。API Key 必须由用户通过控制台创建并注入 Secret 或环境变量；不要要求用户把真实 Key 粘贴到对话，也不要把 Key 写进源码、浏览器代码、日志或 Git。
- 示例中的 Key 和业务数据都是占位值。除非用户明确要求并授权，不要代表用户向线上接口发送写入、更新或删除请求。
- 向用户说明写入是异步同步链路：中心数据写入成功后，区域搜索结果可能稍后才可见。

## 接入前信息清单

开始编码前，确认以下事项：

1. **业务场景**：例如商品目录、帮助中心、FAQ、工单或内部知识条目。
2. **数据来源**：哪个业务服务负责创建、更新和删除数据；采用事件触发还是定时批量同步。
3. **集合与文档**：集合名称、文档字段、稳定且唯一的 `id`，以及需要搜索、过滤和排序的字段。
4. **搜索体验**：关键词、分页、过滤、排序、返回字段和用户所在区域。
5. **运行环境**：后端语言与框架、开发/测试/生产环境，以及 Secret 的注入方式。
6. **权限与凭证**：所需 scope，以及负责创建、保存和轮换 API Key 的人或团队。不要在代码生成或文档中放真实密钥。

## 接入流程

### 01 确认需求与数据模型

先把业务对象映射成可搜索文档。例如商品可以使用 `products` 集合，文档包含商品 ID、名称、类目、价格和上架状态。`id` 应采用业务系统稳定的主键；同一集合内，每条业务文档都必须有 `id`。

判断是否需要全文搜索、简单过滤和排序。如果需求依赖事务一致性、复杂关联查询或实时精确库存，保留业务数据库作为权威数据源，MeliData 用于搜索和检索。

### 02 开通应用并准备 API Key

由客户或平台管理员在 MeliData 控制台创建应用和 API Key。按用途只授予需要的 scope：

| 用途 | scope |
| --- | --- |
| 新增、更新、批量写入、软删除文档 | `data:write` |
| 读取文档或集合数据 | `data:read` |
| 搜索或发现在线区域 Agent | `search:read` |

将 Key 保存在服务端密钥管理系统，并通过环境变量注入。开发、测试和生产环境应使用各自的 Key。

### 03 阅读接口契约并选择接口

编码前先阅读：

- API Reference：<https://meilisearch.1oa.com.cn/open-platform/docs/api-reference>
- OpenAPI JSON：<https://meilisearch.1oa.com.cn/openapi.json>

按业务操作选择 `POST` 写入、批量写入、`GET` 读取、`DELETE` 软删除或区域搜索接口。不要将管理控制台接口当作业务数据 API 使用。

### 04 实现业务调用

把 API Key 从环境变量读取，在服务端发起请求。按下文示例实现所需操作，并按实际字段调整 JSON。单条业务事件使用单条写入；初始化或批量导入使用批量写入。

### 05 按需配置过滤和排序

只有搜索需要过滤或排序时才配置集合设置。字段名称必须与文档字段一致；设置保存后还需要等待区域索引处理同步命令。

### 06 端到端验证

在开发或测试环境用一条测试文档验证完整链路：写入成功 → 等待 CDC/区域 Agent 同步 → 搜索命中。再验证更新会反映到搜索结果，删除后文档不再命中。不要只凭写入接口返回成功就认定搜索链路完成。

### 07 上线与交付

上线前检查 Secret 注入、scope 最小化、重试策略和日志脱敏。交付时说明使用的集合、接口、scope、环境变量名称、验证结果和仍需用户提供的配置；不要在交付内容中回显真实 Key。

## API 地址与认证

当前线上数据 API 和默认区域搜索地址如下：

```text
数据与索引 API 基础地址： https://meilisearch.1oa.com.cn/api/v1
默认区域搜索基础地址：   https://meilisearch.1oa.com.cn/documents/api/v1
```

所有示例地址均为当前线上完整地址。`{collection}` 和 `{id}` 是路径占位符，调用时替换为实际集合名和文档 ID。

在业务服务配置环境变量。下面的 Key 是占位文本，请通过 Secret 管理系统设置真实值：

```bash
export MELIDATA_API_BASE_URL="https://meilisearch.1oa.com.cn/api/v1"
export MELIDATA_SEARCH_BASE_URL="https://meilisearch.1oa.com.cn/documents/api/v1"
export MELIDATA_API_KEY="由 Secret 管理系统注入，不要将真实值提交到代码仓库"
export COLLECTION="products"
```

数据与索引 API 请求使用：

```http
Authorization: Bearer $MELIDATA_API_KEY
Content-Type: application/json
```

## 接口速查：什么场景调用什么接口

| 场景 | 方法与完整地址 | scope |
| --- | --- | --- |
| 创建或更新一条文档 | `POST https://meilisearch.1oa.com.cn/api/v1/data/{collection}` | `data:write` |
| 批量导入或更新文档 | `POST https://meilisearch.1oa.com.cn/api/v1/data/{collection}/batch` | `data:write` |
| 按 ID 读取文档 | `GET https://meilisearch.1oa.com.cn/api/v1/data/{collection}/{id}` | `data:read` |
| 分页读取集合文档 | `GET https://meilisearch.1oa.com.cn/api/v1/data/{collection}?limit=20&offset=0` | `data:read` |
| 软删除文档 | `DELETE https://meilisearch.1oa.com.cn/api/v1/data/{collection}/{id}` | `data:write` |
| 配置过滤和排序字段 | `POST https://meilisearch.1oa.com.cn/api/v1/indexes/{collection}/settings` | `data:write` |
| 默认区域搜索 | `POST https://meilisearch.1oa.com.cn/documents/api/v1/collections/{collection}/search` | `search:read` |
| 查询在线区域 Agent | `GET https://meilisearch.1oa.com.cn/api/v1/agents/online` | `search:read` |

## 接口调用示例

### 新增或更新单条文档

适用于业务服务收到商品、文章、FAQ 等对象的创建或变更事件。相同 `id` 的后续写入会更新该文档。

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

本例完整地址为 `https://meilisearch.1oa.com.cn/api/v1/data/products`。请求体必须含 `id`；成功响应中的文档信息位于 `data` 字段。

### 批量导入或更新文档

适用于首次导入、周期同步或一次处理多条业务变更。每个元素必须包含唯一 `id`。

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

本例完整地址为 `https://meilisearch.1oa.com.cn/api/v1/data/products/batch`。单次最多 1000 条，请求体不超过 5 MiB；同一批次内的 `id` 不可重复。更大的数据集请拆分批次。

### 按 ID 读取文档

适用于业务后台检查已写入的中心数据。面向终端用户的全文检索请使用区域搜索接口。

```bash
curl --fail-with-body -sS \
  "$MELIDATA_API_BASE_URL/data/$COLLECTION/sku-001" \
  -H "Authorization: Bearer $MELIDATA_API_KEY"
```

本例完整地址为 `https://meilisearch.1oa.com.cn/api/v1/data/products/sku-001`。

### 分页读取集合文档

适用于后台核对数据或开发期抽样检查；不要用循环逐页拉取替代批量导出方案。

```bash
curl --fail-with-body -sS \
  "$MELIDATA_API_BASE_URL/data/$COLLECTION?limit=20&offset=0" \
  -H "Authorization: Bearer $MELIDATA_API_KEY"
```

本例完整地址为 `https://meilisearch.1oa.com.cn/api/v1/data/products?limit=20&offset=0`。`limit` 范围为 1–100，`offset` 从 0 开始。

### 删除文档

适用于业务对象被下架、撤回或删除。接口执行软删除，删除变更随后经 CDC 同步到区域索引。

```bash
curl --fail-with-body -sS -X DELETE \
  "$MELIDATA_API_BASE_URL/data/$COLLECTION/sku-001" \
  -H "Authorization: Bearer $MELIDATA_API_KEY"
```

本例完整地址为 `https://meilisearch.1oa.com.cn/api/v1/data/products/sku-001`，需要 `data:write`。

### 配置过滤和排序字段

当搜索需要按类目或状态筛选，并按价格排序时，先注册这些字段：

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

本例完整地址为 `https://meilisearch.1oa.com.cn/api/v1/indexes/products/settings`。成功响应表示中心配置已保存，不表示区域节点已经完成同步。

### 区域搜索

面向终端用户提供搜索时，调用区域 Agent。默认线上入口是天津区域：

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

本例完整地址为 `https://meilisearch.1oa.com.cn/documents/api/v1/collections/products/search`。搜索结果位于响应的 `data.hits` 中。多区域部署应按用户区域选择对应 Agent 地址；单区域场景直接使用默认入口即可。

### 发现在线区域 Agent

当应用需要根据用户所在区域路由搜索请求时，可先查询在线节点；若已经由部署配置确定唯一搜索入口，则不需要调用此接口。

```bash
curl --fail-with-body -sS \
  "https://meilisearch.1oa.com.cn/api/v1/agents/online" \
  -H "Authorization: Bearer $MELIDATA_API_KEY"
```

多区域情况下，可按响应中的区域信息和业务路由规则选择搜索地址。不要将 Meilisearch 服务凭证暴露给业务调用方。

## 推荐使用场景

- **商品目录搜索**：商品名称、品牌、类目和描述写入 `products`；按需配置类目筛选和价格排序。
- **帮助中心与 FAQ**：标题、正文、产品线、语言和发布状态写入 `articles` 或 `faqs`；内容发布或修改后更新文档，再通过区域搜索查找。
- **内部制度和知识库**：将可搜索的条目及部门、文档类型、发布日期等字段写入集合；敏感文档应在业务侧做好授权与结果权限校验。
- **工单、缺陷和项目记录**：写入标题、描述、编号、状态和负责人；按需配置状态或项目筛选。
- **多区域产品**：中心业务服务负责写入，用户请求发往就近 Agent，减少跨区域搜索延迟。

MeliData 适合全文检索、关键词查找和简单过滤/排序。订单结算、库存扣减等需要强事务一致性的操作仍由业务数据库负责。搜索索引通过 CDC 异步更新，因此写入成功后搜索结果可能稍后才可见。建议先使用少量样例验证字段、权限和搜索效果，再批量导入数据。

## 开发与上线建议

1. 以业务边界划分集合，例如 `products`、`faqs`、`tickets`；为每条文档指定稳定 ID。
2. 仅申请代码实际需要的 scope；为开发、测试和生产环境分别管理 Key。
3. 将 Key 存入服务端 Secret 管理系统。浏览器和移动端不要直接持有业务 API Key，应由自己的后端代为调用。
4. 事件触发适合实时单条写入；初始化或周期任务适合批量写入。对限流或临时服务错误使用有限次数的退避重试。
5. 验收时覆盖新增、更新、删除和搜索，并为异步同步预留等待时间。
6. 过滤、排序只使用已配置的字段；其他查询参数按当前 API Reference 与 OpenAPI 定义实现。
7. 日志记录请求 ID、集合名和结果状态即可，不要记录 API Key 或完整敏感文档内容。

## 在线参考

- 首页接入总览：<https://meilisearch.1oa.com.cn/open-platform/docs/how-to-use>
- API Reference：<https://meilisearch.1oa.com.cn/open-platform/docs/api-reference>
- AI Agent 集成指南：<https://meilisearch.1oa.com.cn/open-platform/docs/agent-guide>
- 快速开始：<https://meilisearch.1oa.com.cn/open-platform/docs/quickstart>
- OpenAPI JSON：<https://meilisearch.1oa.com.cn/openapi.json>
