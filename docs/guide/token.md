# Token / JWT 校验说明

本项目中，UniData（Python 服务）与 meilisearch-sync-service（Go 服务）共用一套自实现的 **HS256 JWT** 协议，用于标识「调用方应用」并做权限隔离。

## 一、签名算法与密钥

- **算法**：`HS256`（HMAC-SHA256）
- **密钥来源**：
  - UniData：`app/core/config.py` 中的 `Settings.jwt_secret`
  - meilisearch-sync-service：`internal/config/config.go` 中的 `AppConfig.JWTSecret`
- **默认值**：`please-change-me-in-prod`（应在生产环境中通过环境变量覆盖）

**要求**：两个服务使用 **相同的 jwt_secret/JWT_SECRET**，这样任一服务生成的 token 都能被另一端校验。

## 二、JWT 的生成脚本

脚本位置：`UniData/scripts/generate_jwt.py`

### 核心逻辑

**Header**：

```json
{ "alg": "HS256", "typ": "JWT" }
```

**Payload 字段**：

```json
{
  "app_name": "myapp",        // 应用名称，用于索引前缀
  "scopes": ["testcases:read"], // 权限范围列表（可为空）
  "exp": 1730000000           // 过期时间（秒级时间戳）
}
```

**签名**：
1. 使用 `jwt_secret` 作为 key，对 `base64url(header) + "." + base64url(payload)` 做 HMAC-SHA256。
2. 结果再做 base64url 编码，拼为 `header.payload.signature`。

### 常用 TTL 常量（秒）

- `TTL_SHORT = 3600`：1 小时
- `TTL_DAY = 86400`：1 天
- `TTL_WEEK = 604800`：1 周
- `TTL_MONTH = 2592000`：30 天
- `TTL_YEAR = 31536000`：1 年
- `TTL_LONGTERM = 315360000`：10 年

### 命令行使用示例

```bash
cd UniData

# 生成 app 为 myapp，默认长期（10 年）有效的 token
python scripts/generate_jwt.py --app-name myapp

# 指定 scopes 和有效期（1 天）
python scripts/generate_jwt.py \
  --app-name myapp \
  --scopes testcases:read,indexes:read \
  --ttl 86400
```

脚本会在标准输出打印生成的 JWT，可以手动复制到配置或工具中使用，例如根目录的 `token.txt`。

## 三、Python 侧（UniData）的 token 解析与校验

模块位置：`UniData/app/core/auth.py`

### 关键函数

- `_decode_jwt(token, secret, algorithms=["HS256"])`
  - 拆分 `header.payload.signature`
  - base64url 解码并解析 header / payload
  - 校验 `alg` 是否在允许列表（默认仅 `HS256`）
  - 使用 `jwt_secret` 对 `header.payload` 重新计算签名并对比
  - 校验 `exp`（如存在），当前时间 ≥ `exp` 则视为过期
- `get_current_app(...) -> AppIdentity`
  - 从请求头读取：
    - `Authorization: Bearer <jwt>`
    - `X-App-Name`（可选）
  - 解析并校验 token
  - 从 payload 中提取：
    - `app_name`（或 `sub`）
    - `scopes` / `scope`（字符串或数组，统一为 `List[str]`）
  - 如 `X-App-Name` 存在且与 payload 中的 `app_name` 不一致，则拒绝
  - 返回 `AppIdentity(app_name, scopes)`

FastAPI 路由可以通过依赖 `get_current_app` 获取当前调用方应用身份，用于业务层做权限控制。

## 四、Go 侧（meilisearch-sync-service）的 token 解析与校验

模块位置：`meilisearch-sync-service/internal/auth/auth.go`

### 关键函数

- `DecodeJWT(token string, secret string) (map[string]interface{}, error)`
  - 与 Python 逻辑对应：
    - 拆分三段，base64url 解码 header/payload
    - 校验 `alg == "HS256"`
    - 使用 `secret` 对 `header.payload` 做 HMAC-SHA256，比对签名
    - 校验 `exp` 是否过期
- `IdentityFromToken(token string, secret string) (AppIdentity, error)`
  - 从 payload 中解析：
    - `app_name`（或 `sub`），映射到 `AppIdentity.AppName`
    - `scopes` / `scope`，统一为 `[]string`，映射到 `AppIdentity.Scopes`
  - 若缺少 `app_name`（且 `sub` 也为空），视为非法 token

### 在搜索代理 handler 中的使用

- 文件：`meilisearch-sync-service/internal/handler/handler.go`
- 入口 `NewSearchHandler` 会：
  - 从 HTTP 头读取 `Authorization: Bearer <jwt>`
  - 调用 `IdentityFromToken(token, cfg.JWTSecret)` 验证 token
  - 根据 `identity.AppName` 以及配置 `MeiliIndex` 计算实际索引名：
    ```
    indexUID = <AppName>_<MeiliIndex>   # 当 AppName 非空时
    indexUID = MeiliIndex               # 否则
    ```
  - 将调用方请求体透传到 Meilisearch 对应索引的 `/indexes/{indexUID}/search` 接口

## 五、自助申请 Token (Web UI)

### 1. 页面功能

该页面是一个纯静态 HTML 文件，基于 Layui 构建，提供了以下功能：

- **发起申请**：填写应用名称、失效日期、接收人 ITCode。
- **进度查询**：查看待审核的申请列表。
- **注册公示**：查看已通过审核的注册服务列表。

### 2. 使用步骤

1. **打开页面**：
   在浏览器中打开 `app_token_register.html`（需确保能访问到后端 API，默认 `/api/v1/...`）。

2. **提交申请单**：
   - **应用名称 (`app_name`)**：唯一标识，将作为数据隔离的依据（如 `payment-service`）。
   - **失效日期**：Token 的过期时间。
   - **接收人**：Token 生成后通知的目标用户。

3. **后台审核**：
   申请提交后状态为 `pending`。管理员审核通过后，状态变为 `approved`，Token 即刻生效。

### 3. 对应后端接口

页面交互主要依赖以下 API（详见 API 文档）：

- `POST /api/v1/auth/token`: 提交申请
- `GET /api/v1/auth/tokens/pending`: 轮询待审核列表
- `GET /api/v1/auth/tokens/approved`: 获取已注册服务
