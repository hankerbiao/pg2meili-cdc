# 代码评审报告 — 最近 24 小时变更

- **仓库**：`pg2meili-cdc`
- **评审窗口**：2026-08-04 ~ 2026-08-05（最近 24 小时）
- **Diff 基准**：`8964d21` → `ddaa804`（16 个 commit）
- **规模**：57 个文件，+3767 / -112 行
- **区域**：Backend `UniData`（24 文件）/ Frontend `open-platform-web`（27 文件）/ 构建与配置（`dev.sh`、`docker-compose.yml`、docs、playwright、`.superpowers`）
- **方法**：基于 `git diff` 逐区域审查 + 对关键安全/越权声明逐条亲验（`App.tsx` / `ConsoleLayout.tsx` / `open_platform.py` / `oa_auth.py` / `oa.py` / `any_auth.py`）
- **产出**：本报告，**未改动任何代码**

---

## 一、严重度汇总

| 严重度 | 数量 | 条目 |
|---|---|---|
| Blocker | 0 | —（原"前端越权"经亲验降级为 Medium，见 §3.1） |
| High | 2 | B-1 OA 安全模型零测试覆盖；I-1 compose env_file 覆盖致 CORS 静默失效 |
| Medium | 11 | 见下文各区域 |
| Low | 6 | 见下文各区域 |

> 说明：本次窗口**未发现数据泄露级漏洞**。后端对 `/audit-logs`、`/agents`、`/users` 均强制 admin（`get_admin_session` / `require_admin_csrf`），OA 用户即使直达前端页面，API 也返回 403。问题集中在**纵深防御、功能偏离、配置遮蔽与测试缺口**。

---

## 二、后端（UniData / FastAPI）

### B-1 【High】OA 安全模型零自动化测试覆盖
- **位置**：`UniData/tests/test_open_platform.py`、`test_open_platform_caller_e2e.py`
- **问题**：新引入的全部 OA 安全不变量都没有测试驱动：`get_any_session` 的 owner 过滤、`_assert_owned` 跨 owner 读返回 403、OA `create_app` 强制本人、禁用用户 401 拦截、OA 写操作免 CSRF。现有测试只走 admin 路径。
- **修复**：用伪造 `unidata_oa_session` cookie（`create_oa_session`）补充用例：①`GET /apps` 仅返回本人应用；②读他人 app → 403；③禁用用户访问控制台端点 → 401；④OA 写请求**不带** `X-CSRF-Token` 应成功。

### B-2 【Medium】OA 禁用用户在 `/oa/me` 未被拦截
- **位置**：`UniData/app/core/oa_auth.py:128-134`（`get_oa_user`）；`UniData/app/api/v1/endpoints/oa.py:123-136`（`/oa/me`）
- **问题**：`get_oa_user` 仅调用 `decode_oa_session`（校验签名+过期），**从不查 `OaUser.status`**。而禁用检查只存在于 `get_any_session`（`any_auth.py:69-70`）。结果：被管理员禁用的 OA 用户仍可调用 `/oa/me` 取回个人资料。
- **修复**：在 `get_oa_user` 内补 `OaUser.status == 'disabled' → 401`，或让 `/oa/me` 改走 `get_any_session`。

### B-3 【Medium】"admin 优先不回退 OA" 可能永久锁死 OA 用户
- **位置**：`UniData/app/core/any_auth.py:55-63`
- **问题**：若请求带 `open_platform_session` cookie 但已过期/被篡改，`decode_admin_session` 抛 401 且**不回退**到 OA。当 OA 用户与管理员会话 cookie 共享浏览器/同域时，OA 用户会被永久 401 锁死，尽管持有有效 OA cookie。
- **修复**：admin cookie 解码失败时**回退**到 OA 分支，而非直接 401（保留"解码成功才视为 admin"的身份安全前提）。

### B-4 【Medium】`SameSite=Strict` 破坏跨源 SPA 登录
- **位置**：`oa.py:74-82,111-119`（OA 与管理员会话 cookie 均 `samesite="strict"`）
- **问题**：`.env.example` 启用 `CORS_ALLOW_ORIGINS=http://localhost:3100`（独立源 SPA）。`Strict` 下浏览器在跨站请求**不发送**会话 cookie，登录态失效；OA 免 CSRF 的设计也完全依赖 `Strict`。
- **修复**：同源 SPA 场景改用 `SameSite=Lax`；或文档明确"仅支持同源部署"。

### B-5 【Medium】重新启用用户不复活级联禁用的应用
- **位置**：`UniData/app/api/v1/endpoints/open_platform.py:488-517`
- **问题**：禁用用户会将其名下 active 应用级联置 `disabled`（正确，拒绝其 API Key）；重新启用**有意不**复活这些应用。需确认这是期望 UX 并文档化，否则应用处于"孤儿禁用"态。
- **修复**：文档说明；若需自动复活，在启用时同步复活（并审计）。

### B-6 【Medium】`test_open_platform` 缺少负向/隔离断言
- **位置**：`UniData/tests/test_open_platform.py:97,125`
- **问题**：断言了 admin 本人 owner，但无用例验证"OA 会话传入他人 owner 被忽略/拒绝"，也无 `_assert_owned` 阻止跨 owner 读取的断言。
- **修复**：补充跨 owner 隔离的负向用例。

### B-7 【Low】JWT 验签失败日志泄露 PII
- **位置**：`oa.py:64,68`
- **问题**：`logger.warning(..., payload[:80])` 记录了含 OA 个人信息的签名 JWT 头部。
- **修复**：仅记录错误原因，不记录 payload。

### B-8 【Low】GET `/oa/login` 将 JWT 置于 URL
- **位置**：`oa.py:40-91`
- **问题**：回调 JWT 经 query string 传递（浏览器历史/Referer/访问日志可留痕）。已有 POST `/oa/callback`。
- **修复**：优先 POST；若保留 GET，不要记录 token。

### B-9 【Low】GET 回调未捕获非 HTTPException
- **位置**：`oa.py:56-86`
- **问题**：仅捕获 `decode_and_verify_oa_jwt` 的 `HTTPException`；`upsert_oa_user` 的 DB 错误会冒泡为 500 + traceback。
- **修复**：回调体包 try/except → 友好 302 回登录页。

### 已核实无问题（后端）
- **注入**：所有 repository 与迁移均用 ORM 或参数化 `text(...)`；唯一原始 SQL `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 为静态无插值。✅
- **迁移幂等**：`create_all` + `ALTER ... IF NOT EXISTS`（`migrate_open_platform.py:42,57`）对新旧部署均幂等。✅
- **密钥**：`.env.example` 用占位符；`oa_jwt_secret` / `open_platform_session_secret` 支持 `*_FILE` Docker 密钥。✅（提示：OA **会话** cookie 用 `open_platform_session_secret` 签名，非 `oa_jwt_secret`，建议文档注明。）

---

## 三、前端（open-platform-web / React）

### F-1 【Medium】管理后台路由未做角色鉴权（纵深防御缺口）
- **位置**：`src/App.tsx:21-27`（`ProtectedRoute` 仅 `if (!user)`）；`src/App.tsx:55-58`（`agents`/`audit`/`users` 嵌套其下）；`src/components/ConsoleLayout.tsx:15-21`（仅隐藏 NavLink）
- **问题**：OA 用户可直接访问 `/console/audit`、`/console/users`、`/console/agents`，页面壳可达。**亲验结论**：后端 `/audit-logs`(`open_platform.py:337`)、`/agents`(`:346`) 用 `get_admin_session`，`/users` 用 `require_admin_csrf`，故 **API 返回 403、数据不泄露**；但 OA 用户能看到"无权限"的错误页，属 UX/纵深防御缺陷。
- **修复**：增加 `RequireAdmin` 路由守卫，或各页内 `if (user?.role !== 'admin') return <Navigate to="/console/apps" />`。

### F-2 【Medium】admin 可指定 owner 未实现（功能偏离）
- **位置**：`src/pages/AppsPage.tsx:73-77`；后端 `open_platform.py:219-220,244-245`
- **问题**：前端 `owner_itcode: user!.username` 硬编码且无 owner 输入项；后端 `create_app`/`bootstrap_app` 注释明确"请求体 owner_itcode 一律忽略"并强制本人。这**与项目记忆记载意图（"admin can set owner, OA fixed to self"）冲突**——admin 代建他人应用的能力在前后端均未实现。
- **修复**：若确需 admin 代建，后端放开 owner 入参（当前忽略）、前端为 admin 渲染 owner 输入框，OA 仍固定本人。

### F-3 【Medium】AuthContext 非 401 错误跳过 OA 回退
- **位置**：`src/auth/AuthContext.tsx:39-51`
- **问题**：仅当 `error instanceof ApiError && status === 401` 才回退 `oaApi.me()`；网络故障（`TypeError`）或 5xx 走 `else if (active) setUser(null)`，瞬时登出 OA 用户并重定向登录页。
- **修复**：非 401 分支也应尝试 `oaApi.me()`，失败再置 null。

### F-4 【Medium】ApiPlaygroundPage `baseUrl` 用户可控致 API Key 外泄
- **位置**：`src/pages/ApiPlaygroundPage.tsx:78,118,123`
- **问题**：`baseUrl` 默认可编辑（默认 `window.location.origin`），发送时 `Authorization: Bearer ${apiKey}` 会发往任意输入主机；填外部地址即泄露密钥。
- **修复**：限制为同源或允许列表；至少对跨域目标给出醒目警告。

### F-5 【Low】OaCallbackPage `next` 参数未校验
- **位置**：`src/pages/OaCallbackPage.tsx:21`
- **问题**：`params.get('next')` 直接传入后端，需后端做 allowlist 防 open-redirect（前端成功恒跳 `/console`，但参数仍发往后端）。
- **修复**：前端对 `next` 做 `startsWith('/console')` 校验（参照 `LoginPage.tsx:13`）。

### F-6 【Low】clipboard 兜底 textarea 短暂入 DOM
- **位置**：`src/utils/clipboard.ts:18-28`
- **问题**：`execCommand` 兜底把含密钥的 textarea 插入 body（offscreen），可被同页脚本/扩展读取。HTTPS 下走 `navigator.clipboard`，影响很小，可接受。
- **修复**：仅记录；若要求严格，可用临时 `range` + `execCommand('copy')` 避免持久节点。

### 已核实无问题（前端）
- **XSS**：全仓 grep `dangerouslySetInnerHTML` 零命中；`ApiPlaygroundPage`/`CodeBlock`/响应均经 React 文本节点渲染。✅
- **旧 `session` 字段**：grep 确认页面/context 已无 `session` 字段引用（仅 `AuthContext` 内局部变量）；`AppsPage.test.tsx:23` 已用 `user:{role:'admin',...}`，**未用旧字段**（修正子代理误报）。✅
- **空/错误态**：`UsersPage`/`AgentsPage`/`AppsPage`/`AppDetailPage` 均处理 `isLoading`/`isError`/空数组。✅
- **PythonSdkPage.test.tsx**：不在本次 diff，其既有失败与本窗口无关。✅

---

## 四、构建与配置

### I-1 【High】`docker-compose.yml` env_file 被 environment anchor 覆盖（CORS 静默失效）
- **位置**：`docker-compose.yml:5-15` + `:185-189`（`unidata`/`unidata-migrate` 同时设 `env_file: ./.env.docker` 与 `environment: <<: *x-unidata-environment`）
- **问题**：Compose 优先级 `environment:` **覆盖** `env_file:`，且 `${VAR:-default}` 从 **shell/根 `.env`** 插值，而非 `.env.docker`。结果 `.env.docker` 中与 anchor 重复的键成为**死配置**：`CORS_ALLOW_ORIGINS`（`:22` 意图追加 `http://127.0.0.1:8080`）、`PG_CONN_STRING`、`LOG_LEVEL`、`KAFKA_API_KEY_TOPIC`。具体后果：`127.0.0.1` 源的 CORS 会被拒（anchor 默认只有 `localhost:8080`）。
- **修复**：从 `x-unidata-environment` anchor 移除这些重复键，让 `.env.docker` 成为单一来源；或把真实值放进根 `.env`（nginx 文档已让用户改根 `.env`，故 `.env.docker` 的对应行是误导性死配置）。

### I-2 【Medium】`dev.sh build --no-cache` 参数解析断裂
- **位置**：`dev.sh:263-265`
- **问题**：`./dev.sh build --no-cache`（省略 target）→ `${2:-}` 为空 → `TARGET=--no-cache` → 落入 `*` → `die`。`--no-cache` 仅在显式 target 之后才生效。
- **修复**：扫描所有参数识别 `--no-cache`，与 target 解耦。

### I-3 【Medium】`.superpowers` 任务简报硬编码错误 DB host
- **位置**：`.superpowers/sdd/user-management/task-1-brief.md:20`
- **问题**：`DATABASE_URL=...@127.0.0.1:5432/...`，但迁移在 `unidata-migrate` 容器内执行，DB host 应为 `postgres` 而非 `127.0.0.1` → 照做连不上。`:87` 绝对本地路径泄露用户名/仓库布局。
- **修复**：改为 `postgresql+asyncpg://postgres:change-me@postgres:5432/postgres`；路径改相对。

### I-4 【Low】`dev.sh` 健壮性
- **位置**：`dev.sh:129`（`kill -0` 空/陈旧 PID 打印 usage）、`:168-171`（`dev go` 每秒递归 `$GO_DIR` 仅过滤 `.git`，未排除 `node_modules`/`vendor`）
- **修复**：PID 非空/数字校验；递归排除大型子树。

### I-5 【Low/Info】`vite.config.ts:11-13` proxy 硬编码 `127.0.0.1:8080`
- 与 8080 统一一致，`dev.sh:102-104` 已对端口不符告警；可接受，仅灵活性低。

### 已核实无问题（配置）
- **playwright.config / global-setup / test-data**：8081 已全迁 8080；`BASE_URL` 用 `127.0.0.1`（可移植，无 LAN IP）。✅
- **docs/nginx-http-domain-setup.md**：准确记录 env_file 覆盖陷阱、cookie/HTTPS 约束、git hygiene；`proxy_pass`/`X-Forwarded-*`/keepalive 正确。✅（可选补 `X-Forwarded-Host`）
- **gitignore**：`git check-ignore` 确认 `.env.docker` 与 `meilisearch-sync-service_go` 均被忽略 → 密钥/二进制未入库。⚠️ 11MB 二进制仍在 **git 历史**（`53f378f` 等），需 rebase/force-push 清除——本报告仅记录，不修。
- **CLAUDE.md**：无密钥、无坏指令；`localhost:8080` 引用一致。✅

---

## 五、优先修复清单（按严重度）

1. **I-1（High）** 修正 compose env_file/anchor 覆盖，恢复 `.env.docker` 的 CORS/PG 配置生效。
2. **B-1（High）** 补 OA 安全模型自动化测试（owner 隔离、禁用拦截、CSRF 豁免）。
3. **B-2（Medium）** `/oa/me` 增加禁用用户拦截。
4. **F-1（Medium）** 前端 admin-only 路由加 `RequireAdmin` 守卫。
5. **F-2（Medium）** 明确并实现"admin 可指定 owner"（前后端一致放开或一致强化本人）。
6. **B-3 / F-3（Medium）** 修正 admin/OA 会话回退逻辑，避免 OA 用户被误锁或瞬时登出。
7. **B-4（Medium）** 评估 `SameSite=Strict` 对跨源 SPA 的影响，必要时改 `Lax` 或限定同源部署。
8. **I-2 / I-3（Medium）** 修复 `dev.sh` 参数解析与 `.superpowers` 简报 DB host。
9. **F-4（Medium）** 限制 ApiPlayground `baseUrl` 防密钥外泄。
10. **B-5/B-6、B-7~B-9、F-5/F-6、I-4/I-5（Low）** 按需清理。

---

## 六、评审备注
- 本次窗口**无数据泄露级漏洞**；后端 admin 强制在 `/audit-logs`、`/agents`、`/users` 已落实。
- 2 项子代理初判经亲验修正：①"前端越权 Blocker"降级为 Medium（后端已拦数据）；②"OA 写缺 CSRF 风险"为误报（`require_any_csrf` 对 OA 显式豁免）。
- 1 项功能偏离需产品/owner 确认意图：admin 代建应用（owner 参数）当前在前后端均未实现，与项目记忆记载设计不符。
