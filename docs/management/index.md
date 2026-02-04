# 数据管理

本模块说明 UniData Producer Service 提供的索引与文档管理接口，覆盖索引列表查询、索引删除，以及通用文档的增删改查。

## 术语说明（统一口径）

- `collection`：业务集合名称（写入与管理的数据维度）
- `index`：搜索索引名称（通常与 collection 对应）
- `app_name`：应用隔离维度，不同应用的数据互相隔离

## 服务信息

- **服务名称**：UniData Producer Service
- **接口协议**：HTTPS / HTTP
- **默认版本**：v1

## 接入地址

- **基础地址（示例）**：`http://localhost:8080`
- **统一前缀**：`/api/v1`

完整调用示例：

```text
http://localhost:8080/api/v1/{resource}
```

## 通用说明

- **鉴权**：本模块接口均需要携带 `Authorization: Bearer <token>`。
- **幂等更新**：同一 `collection` 下相同 `id` 会覆盖更新。
- **同步延迟**：写入成功后会异步同步到搜索端，存在一定延迟（与环境负载相关）。

## 命名与使用约束

- `collection` 不能包含空格。
- 单次批量写入建议控制在合理规模（如 1000 条以内），避免请求体过大导致超时。

## 接口总览

| 模块 | 接口 | 方法 | 描述 |
| :--- | :--- | :--- | :--- |
| 索引管理 | `/api/v1/indexes` | GET | 获取当前应用下的索引列表 |
| 索引管理 | `/api/v1/indexes/{collection}` | DELETE | 删除索引并逻辑删除集合内文档 |
| 索引管理 | `/api/v1/indexes/{collection}/settings` | POST | 设置索引可过滤/可排序字段 |
| 通用文档管理 | `/api/v1/data/{collection}` | POST | 创建或更新文档 |
| 通用文档管理 | `/api/v1/data/{collection}/batch` | POST | 批量创建或更新文档 |
| 通用文档管理 | `/api/v1/data/{collection}/{id}` | GET | 获取单个文档详情 |
| 通用文档管理 | `/api/v1/data/{collection}/{id}` | DELETE | 删除（逻辑删）文档 |
| 通用文档管理 | `/api/v1/data/{collection}` | GET | 分页列出集合内文档 |

---

## 索引管理接口

### 1. 获取索引列表

- **接口地址**：`GET /api/v1/indexes`
- **接口说明**：返回当前应用在 UniData 中已使用的 `collection` 名称列表。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `limit` | int | Query | 否 | `100` | 返回数量，默认 100，最大 500 |
| `offset` | int | Query | 否 | `0` | 偏移量，从 0 开始 |

**请求示例**：

```bash
curl -X GET "http://localhost:8080/api/v1/indexes?limit=100&offset=0"
```

#### 返回结果

返回一个字符串列表：

```json
["testcases", "requirements", "bugs"]
```

### 2. 删除索引并逻辑删除集合内文档

- **接口地址**：`DELETE /api/v1/indexes/{collection}`
- **接口说明**：删除指定 `collection` 的索引，并将集合内文档标记为 `is_delete=true`。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `collection` | string | Path | 是 | `requirements` | 集合名称 |

**请求示例**：

```bash
curl -X DELETE "http://localhost:8080/api/v1/indexes/requirements"
```

#### 返回结果

```json
{
  "status": "success",
  "collection": "requirements",
  "deleted_count": 128
}
```

### 3. 设置索引可过滤/可排序字段

- **接口地址**：`POST /api/v1/indexes/{collection}/settings`
- **接口说明**：设置索引的可过滤与可排序字段，服务端会通过 Kafka 同步到各地 Meilisearch。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `collection` | string | Path | 是 | `movies` | 集合名称 |
| `filterableAttributes` | string[] | Body | 是 | `["genre", "director"]` | 可过滤字段 |
| `sortableAttributes` | string[] | Body | 是 | `["release_date"]` | 可排序字段 |

**请求示例**：

```bash
curl -X POST "http://localhost:8080/api/v1/indexes/testcases/settings" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_JWT>" \
  -d '{
    "filterableAttributes": ["author"],
    "sortableAttributes": ["author"]
  }'
```

#### 返回结果

```json
{"status":"success","collection":"testcases","index_uid":"libiao_testcases"}
```

---

## 通用文档管理接口

该模块提供针对任意集合（`collection`）的通用 CRUD 能力，用于管理测试用例、需求、缺陷等业务数据。

### 1. 创建 / 更新文档

- **接口地址**：`POST /api/v1/data/{collection}`
- **接口说明**：在指定集合中创建或更新文档。请求体必须包含 `id` 字段，其余字段将原样写入数据库。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `collection` | string | Path | 是 | `testcases` | 集合名称（不能包含空格） |
| `id` | string | Body | 是 | `tc_001` | 文档唯一标识 |
| 其他业务字段 | any | Body | 否 | `title`, `status` | 任意 JSON 字段，将作为 payload |

**请求示例**：

```bash
curl -X POST "http://localhost:8080/api/v1/data/testcases" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "tc_001",
    "title": "登录功能测试",
    "priority": "high",
    "status": "active"
  }'
```

#### 返回结果

返回模型：`DocumentResponse`

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `status` | string | 固定为 `success` |
| `id` | string | 文档 ID |
| `collection` | string | 集合名称 |

**返回示例**：

```json
{
  "status": "success",
  "id": "tc_001",
  "collection": "testcases"
}
```

### 2. 获取文档详情

- **接口地址**：`GET /api/v1/data/{collection}/{id}`
- **接口说明**：根据集合名和文档 ID 获取完整文档内容。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `collection` | string | Path | 是 | `testcases` | 集合名称 |
| `id` | string | Path | 是 | `tc_001` | 文档 ID |

**请求示例**：

```bash
curl -X GET "http://localhost:8080/api/v1/data/testcases/tc_001"
```

#### 返回结果

返回对象为存储的完整 payload，例如：

```json
{
  "id": "tc_001",
  "title": "登录功能测试",
  "priority": "high",
  "status": "active",
  "collection": "testcases",
  "app_name": "my-app"
}
```

> **说明**：`collection` 和 `app_name` 字段由服务端注入，用于 CDC 与索引路由。

### 3. 批量创建 / 更新文档

- **接口地址**：`POST /api/v1/data/{collection}/batch`
- **接口说明**：批量写入或更新文档。请求体包含 `items` 列表，每个元素必须包含 `id`。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `collection` | string | Path | 是 | `testcases` | 集合名称 |
| `items` | object[] | Body | 是 | 见示例 | 文档列表 |

**请求示例**：

```bash
curl -X POST "http://localhost:8080/api/v1/data/testcases/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      { "id": "tc_001", "title": "登录功能测试", "priority": "high" },
      { "id": "tc_002", "title": "注册功能测试", "priority": "medium" }
    ]
  }'
```

#### 返回结果

```json
{
  "status": "success",
  "collection": "testcases",
  "count": 2,
  "ids": ["tc_001", "tc_002"]
}
```

### 4. 删除文档（逻辑删）

- **接口地址**：`DELETE /api/v1/data/{collection}/{id}`
- **接口说明**：对指定文档执行软删除，后续由 CDC 同步到搜索端。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `collection` | string | Path | 是 | `testcases` | 集合名称 |
| `id` | string | Path | 是 | `tc_001` | 文档 ID |

**请求示例**：

```bash
curl -X DELETE "http://localhost:8080/api/v1/data/testcases/tc_001"
```

#### 返回结果

返回模型同 `DocumentResponse`。

### 5. 分页列出集合文档

- **接口地址**：`GET /api/v1/data/{collection}`
- **接口说明**：按集合分页返回当前应用下的文档列表。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `collection` | string | Path | 是 | `testcases` | 集合名称 |
| `limit` | int | Query | 否 | `20` | 每页数量，默认 20，最大 100 |
| `offset` | int | Query | 否 | `0` | 偏移量，从 0 开始 |

**请求示例**：

```bash
curl -X GET "http://localhost:8080/api/v1/data/testcases?limit=10&offset=0"
```

#### 返回结果

返回一个文档数组，每个元素与 **获取文档详情** 中返回格式类似。

---

## 错误处理与常见状态码

### 常见 HTTP 状态码

| 状态码 | 说明 | 场景示例 |
| :--- | :--- | :--- |
| 200 | 请求成功 | 查询类接口调用成功 |
| 201 | 创建成功 | 创建 / 更新文档成功 |
| 400 | 请求参数错误 | 缺少必填字段、JSON 解析失败等 |
| 401 | 未认证或 Token 无效 | 缺少或错误的 Authorization 头 |
| 403 | 无权限 | 当前应用无访问权限 |
| 404 | 资源不存在 | 文档或集合不存在 |
| 500 | 服务端错误 | 未捕获异常、数据库异常等 |

### 错误返回示例

```json
{
  "detail": "错误信息"
}
```
