# 管理接口 (Management API)

本模块说明 UniData Producer Service 提供的后端管理类 HTTP 接口，格式参考阿里云 SDK 风格，方便统一管理和对接。

## 服务信息

- **服务名称**：UniData Producer Service
- **接口协议**：HTTPS / HTTP
- **默认版本**：v1

## 接入与认证概览

### 1. 接入地址

- **基础地址（示例）**：`http://localhost:8080`
- **统一前缀**：`/api/v1`

完整调用示例：

```text
http://localhost:8080/api/v1/{resource}
```

### 2. 认证方式（JWT）

所有需要鉴权的接口都使用 Bearer Token：

- **请求头**：
  - `Authorization: Bearer <jwt>`
  - 可选：`X-App-Name: <app_name>`，用于与 JWT 中的 `app_name` 做交叉校验

JWT 由后端统一生成，内部字段包括：

- `app_name`：应用名称
- `scopes`：权限列表
- `exp`：过期时间戳（秒）

### 3. 通用返回格式

**接口成功时**：

- **HTTP 状态码**：`2xx`
- **返回体**：
  - 文档类接口：返回业务 JSON 对象
  - 管理类接口：返回结构化 JSON（见各接口说明）

**接口失败时**：

- **HTTP 状态码**：`4xx` 或 `5xx`
- **返回体**为 FastAPI 默认错误结构，例如：

```json
{
  "detail": "错误信息"
}
```

## 接口总览

| 模块 | 接口 | 方法 | 描述 |
| :--- | :--- | :--- | :--- |
| 认证与令牌管理 | `/api/v1/auth/token` | POST | 为应用生成访问令牌 |
| 认证与令牌管理 | `/api/v1/auth/tokens/pending` | GET | 获取待审核 token 列表 |
| 认证与令牌管理 | `/api/v1/auth/tokens/approved` | GET | 获取已审核 token 列表 |
| 认证与令牌管理 | `/api/v1/auth/tokens/{token_id}/approve` | POST | 审核通过指定 token |
| 通用文档管理 | `/api/v1/data/{collection}` | POST | 创建或更新文档 |
| 通用文档管理 | `/api/v1/data/{collection}/{id}` | GET | 获取单个文档详情 |
| 通用文档管理 | `/api/v1/data/{collection}/{id}` | DELETE | 删除（逻辑删）文档 |
| 通用文档管理 | `/api/v1/data/{collection}` | GET | 分页列出集合内文档 |
| 健康检查 | `/health` | GET | 服务健康检查 |

---

## 认证与令牌管理接口

### 1. 为应用生成访问令牌

- **接口地址**：`POST /api/v1/auth/token`
- **接口说明**：根据 `app_name`、`itcode`、`scopes` 和 `ttl` 生成 JWT 令牌，并记录到数据库。真实 Token 内容通过内部渠道（如工权消息）发送给用户。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `app_name` | string | Body | 是 | `my-app` | 应用名称 |
| `itcode` | string | Body | 是 | `alice` | 接收 token 的企业账号 |
| `scopes` | string[] | Body | 否 | `["write:documents"]` | 权限列表 |
| `ttl` | int | Body | 否 | `315360000` | 有效期（秒），默认 10 年 |

**请求示例**：

```http
POST /api/v1/auth/token HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "app_name": "my-app",
  "itcode": "alice",
  "scopes": ["write:documents"],
  "ttl": 315360000
}
```

#### 返回结果

返回模型：`TokenResponse`

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `app_name` | string | 应用名称 |
| `itcode` | string | 接收 token 的账号 |
| `expires_at` | int | 过期时间戳（秒） |

**返回示例**：

```json
{
  "app_name": "my-app",
  "itcode": "alice",
  "expires_at": 1893456000
}
```

> **说明**：实际 JWT 字符串会通过内部消息系统发送，不直接在该接口返回。

### 2. 获取待审核 token 列表

- **接口地址**：`GET /api/v1/auth/tokens/pending`
- **接口说明**：用于运维或管理员查询当前所有尚未审核通过的 token 记录。

#### 请求参数

无额外参数，仅需具备相应后端访问权限。

#### 返回结果

返回列表元素模型：`TokenRecord`

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | string | token 记录 ID |
| `app_name` | string | 应用名称 |
| `itcode` | string | 申请人账号 |
| `expires_at` | string | 过期时间（ISO8601） |
| `created_at` | string | 创建时间（ISO8601） |

**返回示例**：

```json
[
  {
    "id": "tok_001",
    "app_name": "my-app",
    "itcode": "alice",
    "expires_at": "2030-01-01T00:00:00",
    "created_at": "2025-01-01T10:00:00"
  }
]
```

### 3. 获取已审核 token 列表

- **接口地址**：`GET /api/v1/auth/tokens/approved`
- **接口说明**：查询已审核通过的 token 记录，用于审计或排查。

请求参数与返回结果结构与 **获取待审核 token 列表** 一致。

### 4. 审核通过指定 token

- **接口地址**：`POST /api/v1/auth/tokens/{token_id}/approve`
- **接口说明**：将指定 ID 的 token 记录标记为“已审核通过”，并触发内部消息通知，将 JWT 内容发送给申请人。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `token_id` | string | Path | 是 | `tok_001` | token 记录 ID |

**请求示例**：

```http
POST /api/v1/auth/tokens/tok_001/approve HTTP/1.1
Host: localhost:8080
```

#### 返回结果

返回模型同 `TokenResponse`。

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
  -H "Authorization: Bearer <jwt>" \
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
curl -X GET "http://localhost:8080/api/v1/data/testcases/tc_001" \
  -H "Authorization: Bearer <jwt>"
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

### 3. 删除文档（逻辑删）

- **接口地址**：`DELETE /api/v1/data/{collection}/{id}`
- **接口说明**：对指定文档执行软删除，后续由 CDC 同步到搜索端。

#### 请求参数

| 名称 | 类型 | 位置 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `collection` | string | Path | 是 | `testcases` | 集合名称 |
| `id` | string | Path | 是 | `tc_001` | 文档 ID |

**请求示例**：

```bash
curl -X DELETE "http://localhost:8080/api/v1/data/testcases/tc_001" \
  -H "Authorization: Bearer <jwt>"
```

#### 返回结果

返回模型同 `DocumentResponse`。

### 4. 分页列出集合文档

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
curl -X GET "http://localhost:8080/api/v1/data/testcases?limit=10&offset=0" \
  -H "Authorization: Bearer <jwt>"
```

#### 返回结果

返回一个文档数组，每个元素与 **获取文档详情** 中返回格式类似。

---

## 健康检查接口

健康检查接口定义在应用入口：

- `GET /health`

用于探活和监控，不需要鉴权。

**请求示例**：

```bash
curl -X GET "http://localhost:8080/health"
```

**返回示例**：

```json
{
  "status": "healthy"
}
```

---

## 错误处理与常见状态码

### 1. 常见 HTTP 状态码

| 状态码 | 说明 | 场景示例 |
| :--- | :--- | :--- |
| 200 | 请求成功 | 查询类接口调用成功 |
| 201 | 创建成功 | 创建 / 更新文档成功 |
| 400 | 请求参数错误 | 缺少必填字段、JSON 解析失败等 |
| 401 | 未认证或 Token 无效 | 缺少或错误的 Authorization 头 |
| 403 | 无权限 | Token 作用域不足 |
| 404 | 资源不存在 | 文档或 token 记录不存在 |
| 500 | 服务端错误 | 未捕获异常、数据库异常等 |

### 2. 错误返回示例

```json
{
  "detail": "未找到指定的 token"
}
```

---

## 调用示例（汇总）

### 1. 使用 Token 写入测试用例文档

```bash
JWT="<your_jwt_token>"

curl -X POST "http://localhost:8080/api/v1/data/testcases" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "tc_1001",
    "title": "关机场景测试",
    "priority": "P0",
    "tags": ["Linux", "AMD"]
  }'
```

### 2. 查询单个文档

```bash
curl -X GET "http://localhost:8080/api/v1/data/testcases/tc_1001" \
  -H "Authorization: Bearer $JWT"
```

### 3. 分页查询文档列表

```bash
curl -X GET "http://localhost:8080/api/v1/data/testcases?limit=20&offset=0" \
  -H "Authorization: Bearer $JWT"
```

### 4. 删除文档（逻辑删）

```bash
curl -X DELETE "http://localhost:8080/api/v1/data/testcases/tc_1001" \
  -H "Authorization: Bearer $JWT"
```
