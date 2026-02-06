# Token / JWT 校验说明（开发者）

这一节用更直白的方式说明：系统如何识别“是谁在调用”，以及为什么两个服务都能认得同一个 Token。该内容仅面向服务开发与联调，不面向终端用户。

## 一、基本概念

- **Token 就是一串通行证**：带上它，服务才能知道你是谁、能做什么。
- **两个服务共用同一把“钥匙”**：
  - UniData（Python 服务）
  - meilisearch-sync-service（Go 服务）
- **只要钥匙一致**：任一服务生成的 Token，另一端都能验证。

## 二、如何生成 Token

脚本位置：`UniData/scripts/generate_jwt.py`

你只需要传三个核心信息：

- `app_name`：你的应用名称（用于区分不同调用方）
- `scopes`：权限范围（可选）
- `exp`：过期时间

### 常用有效期（秒）

- `TTL_SHORT = 3600`：1 小时
- `TTL_DAY = 86400`：1 天
- `TTL_WEEK = 604800`：1 周
- `TTL_MONTH = 2592000`：30 天
- `TTL_YEAR = 31536000`：1 年

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

## 三、服务端会做哪些校验

无论是 Python 还是 Go 服务，验证逻辑都一样：

- **签名是否正确**：确保 Token 没被篡改
- **是否过期**：过期则直接拒绝
- **应用名是否匹配**：确保请求来自正确的应用

通过校验后，服务会得到：

- `app_name`：调用方应用
- `scopes`：权限范围

如果校验失败，你会看到类似 “未授权 / token 无效 / token 过期” 的错误。

## 四、自助申请 Token (Web UI)

### 1. 页面功能

该页面是一个纯静态 HTML 文件，基于 Layui 构建，提供了以下功能：

- **发起申请**：填写应用名称、失效日期、接收人 ITCode。
- **进度查询**：查看待审核的申请列表。
- **注册公示**：查看已通过审核的注册服务列表。

### 2. 使用步骤

1. **打开页面**：
   在浏览器中打开 `/app/register`（需确保能访问到后端 API，默认 `/api/v1/...`）。
1. **提交申请单**：
   - **应用名称 (`app_name`)**：唯一标识，将作为数据隔离的依据（如 `payment-service`）。
   - **失效日期**：Token 的过期时间。
   - **接收人**：Token 生成后通知的目标用户。
1. **后台审核**：
   申请提交后状态为 `pending`。管理员审核通过后，状态变为 `approved`，Token 即刻生效。

### 3. 对应后端接口

页面交互主要依赖以下 API（详见 API 文档）：

- `POST /api/v1/auth/token`: 提交申请
- `GET /api/v1/auth/tokens/pending`: 轮询待审核列表
- `GET /api/v1/auth/tokens/approved`: 获取已注册服务
