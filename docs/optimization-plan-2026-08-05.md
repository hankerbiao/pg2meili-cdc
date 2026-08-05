# 优化方案设计 — 基于 2026-08-05 代码评审发现

- **输入**：`docs/code-review-2026-08-05.md`（24h 变更评审：0 Blocker / 2 High / 11 Medium / 6 Low）
- **目标**：按"安全边界 → 健壮性 → 体验/清理"排序，给出每项问题的**具体改法**（文件、代码点、验收），并明确需要拍板的决策项
- **原则**：不改变既有产品语义（除非另有拍板）；每个改动可独立提交、可独立回滚；全部带自动化回归

---

## 〇、待拍板决策项（先定这 3 个，影响改动范围）

### D-1 owner 语义：确认"全员强制本人"为最终设计
- **现状**：今天 14:05 已拍板删除"负责人 itcode"输入项，前后端对所有角色强制 `owner_itcode = 登录人`（后端注释"请求体 owner_itcode 一律忽略"）。
- **评审发现**：`MEMORY.md` 仍记载"admin 可填 owner，OA 固定本人"——**已过时**，与现状冲突。
- **建议**：确认现状为最终设计，只修正文档/MEMORY，**不改代码**。若未来要支持 admin 代建：后端 `create_app/bootstrap_app` 放开 owner 入参（`role==admin` 时读请求体）、前端 admin 渲染 owner 输入框（OA 隐藏）——作为独立需求另立，不进本方案。
- **涉及**：`docs/*`、`.workbuddy/memory/MEMORY.md`、`README`（如提及）。

### D-2 SameSite：保持 `Strict`，文档化"同站部署"约束
- **现状**：OA 与管理员会话 cookie 均 `samesite="strict"`（`oa.py:80,117`；admin_auth 同理）。
- **评审发现**：CORS 配置了 `localhost:3100`（vite HMR 跨端口）。**核实结论**：SameSite 只认 scheme+可注册域名，**不看端口**——`localhost:3100 → localhost:8080` 属同站，Strict cookie 正常携带；仅"前端与 API 跨域名"（如 `app.example.com → api.example.com`）才会失效。部署本就同源（nginx 同域托管 `/open-platform`）。
- **建议**：**保持 Strict**（更强防 CSRF），在 `docs/nginx-http-domain-setup.md` 与 `dev.sh dev frontend` 提示中写明"前端必须与 API 同站（同 scheme+域名，端口不限）"。不加代码改动。

### D-3 重新启用用户：保持"不复活应用"，加 UI 提示
- **现状**：disable 级联停用名下 active 应用；enable **有意不**复活。
- **建议**：保持语义；`UsersPage` 启用按钮旁加 hint（"启用后其应用保持禁用，需手动启用"），`/users` 接口文档注明。可选二期：enable 对话框加"同时恢复应用"复选框。

---

## 一、P0 — 安全与正确性（建议第一批实施）

### P0-1【High】补齐 OA 安全模型自动化测试（B-1 / B-6）
- **现状**：`test_open_platform.py` 仅覆盖 admin 路径；OA 全部安全不变量无测试。
- **设计**：新增 `UniData/tests/test_oa_security.py`：
  - **fixture** `oa_client`（仿 `platform_client`）：settings 注入 `open_platform_session_secret="test-session-secret..."`、`oa_cookie_secure=False`；用 `create_oa_session("libiao1", profile)` 伪造 OA cookie 写入 client；用 `upsert_oa_user` 落 OaUser 行（`db_session` 不 commit，测试结束回滚）。
  - **用例**：
    1. `GET /api/v1/open-platform/apps`（OA）→ 仅返回 `owner==libiao1` 的应用
    2. OA 读他人 app `GET /apps/{other_id}` → 403（`_assert_owned`）
    3. OA `POST /apps` 请求体 owner 传 `hacker_attempt` → 201 且返回 owner==`libiao1`（强制本人）
    4. OA `PATCH /apps/{id}` 试图改 owner → 403
    5. OA 写操作**不带** `X-CSRF-Token`（如 `POST /apps`）→ 201（CSRF 豁免）
    6. admin 写操作不带 `X-CSRF-Token` → 403（已有用例，保留）
    7. 禁用用户：OaUser `status='disabled'` + 有效 OA cookie → `GET /apps` 401（`get_any_session` 拦截）
    8. 禁用用户 → `GET /api/v1/auth/oa/me` 401（P0-2 修复后生效）
    9. admin cookie 有效 + OA cookie 同时在 → 身份为 admin
    10. admin cookie **无效** + OA cookie 有效 → 身份为 OA（P0-3 修复后生效）
- **验收**：`TEST_PG_CONN_STRING=... pytest tests/test_oa_security.py -v` 全绿；与既有 12 例无冲突。

### P0-2【Medium】OA 禁用用户在 `/oa/me` 未拦截（B-2）
- **位置**：`UniData/app/core/oa_auth.py:128`（`get_oa_user` 只验签、不查 status）；`UniData/app/api/v1/endpoints/oa.py:123`（`/oa/me`）
- **设计**：在 `oa_service.py` 新增共享助手，`any_auth.py` 与 `/oa/me` 复用（消除重复逻辑）：
  ```python
  # oa_service.py
  async def assert_oa_user_active(db: AsyncSession, itcode: str) -> None:
      """仅当用户存在且 status=='disabled' 时抛 401；不存在视为可访问（与现状一致）。"""
      row = await db.scalar(select(OaUser.status).where(OaUser.itcode == itcode))
      if row == "disabled":
          raise HTTPException(401, "该账号已被禁用，请联系管理员")
  ```
  - `any_auth.py:68-70` 改调 `assert_oa_user_active(db, oa.itcode)`（删除内联 select）
  - `oa.py /oa/me` 在 `get_oa_user_profile` 前调用 `await assert_oa_user_active(db, session.itcode)`
- **验收**：P0-1 用例 8 通过；手动：禁用 `libiao1` 后带 OA cookie `GET /auth/oa/me` → 401。

### P0-3【Medium】admin cookie 失效时不锁死 OA 用户（B-3）
- **位置**：`UniData/app/core/any_auth.py:55-63`
- **问题**：admin cookie 存在但过期/被篡改 → `decode_admin_session` 抛 401 → **不回退 OA**，OA 用户被永久锁死。
- **设计**：decode 失败时**落空继续**走 OA 分支（不再直接 401）：
  ```python
  token = request.cookies.get(SESSION_COOKIE, "")
  if token:
      try:
          admin = decode_admin_session(token)
      except HTTPException:
          pass                      # 无效/过期 → 回退 OA 会话（OA 有效则身份=OA）
      else:
          return AnySession(role=ROLE_ADMIN, username=admin.username, ...)
  # 以下 OA 分支照旧
  ```
  - 安全说明：伪造 admin cookie 且无有效 OA cookie 时，OA 分支最终仍 401；身份混淆风险不变（有效 cookie 才授信）。
- **验收**：P0-1 用例 10 通过；回归：管理员正常登录不受影响。

### P0-4【High】docker-compose 环境变量单源化（I-1）
- **位置**：`docker-compose.yml:5-15`（`x-unidata-environment` 锚点）、`:182-186` / `:200-204`（`env_file` + `environment` 并存）
- **问题**：`environment:` 覆盖 `env_file:`，且 `${VAR:-default}` 由 shell/根 `.env` 插值（非 `.env.docker`）→ `.env.docker` 的 `PG_CONN_STRING/CORS_ALLOW_ORIGINS/LOG_LEVEL/LOG_JSON/LOG_FILE_ENABLED/KAFKA_*` 均为**死配置**；`127.0.0.1:8080` 源会被 CORS 拒。
- **设计**：
  1. **锚点瘦身**：只保留"基础设施内部、不随环境变"的键：`SERVER_PORT: :8080`、`KAFKA_BOOTSTRAP_SERVERS: kafka:9093`、`REDIS_URL: redis://redis:6379/0`；其余（`PG_CONN_STRING`、`CORS_ALLOW_ORIGINS`、`LOG_LEVEL`、`LOG_JSON`、`LOG_FILE_ENABLED`、`KAFKA_API_KEY_TOPIC`、`KAFKA_MEILI_COMMAND_TOPIC`）**全部删除**，交由 `.env.docker` 单源提供。
  2. **修正命名错位**：原锚点 `KAFKA_MEILI_COMMAND_TOPIC: ${KAFKA_COMMAND_TOPIC:-meili.commands}` 变量名与插值源不一致；删除后需确认 `.env.docker` 直接提供 app 实际读取的变量名（对照 `app/core/config.py` 的 env 读取名，实施时核对）。
  3. **dev.sh 插值源一致化**：`dev.sh:29` `COMPOSE="docker compose"` 改为 `COMPOSE="docker compose --env-file .env.docker"`，使 `build/up/watch` 的 `${VAR}` 插值与 `.env.docker` 一致（与历史"改 .env.docker 不生效"的坑彻底告别）。
  4. **文档同步**：`docs/nginx-http-domain-setup.md` 中"陷阱 1"改写为新结论（单源化后无覆盖问题）；删除误导性描述。
- **验收**：
  - `docker compose --env-file .env.docker config | grep -E 'CORS_ALLOW_ORIGINS|PG_CONN_STRING'` 显示 `.env.docker` 真值
  - `./dev.sh build unidata` 起容器后 `docker compose exec unidata env | grep CORS_ALLOW_ORIGINS` 正确
  - 浏览器以 `http://127.0.0.1:8080` 访问控制台，写操作不被 CORS 拒
  - migrate 容器正常 exit 0（PG_CONN_STRING 生效）

### P0-5【Medium】前端 admin-only 路由守卫（F-1）
- **位置**：`open-platform-web/src/App.tsx:21-27`（`ProtectedRoute` 仅查 `user`）、`:55-58`（agents/audit/users 路由）
- **现状核实**：后端已强制 admin（数据不泄露），此为纵深防御 + UX。
- **设计**：新增 `RequireAdmin` 守卫并把 3 条路由包进去：
  ```tsx
  function RequireAdmin() {
    const { user, loading } = useAuth()
    const location = useLocation()
    if (loading) return <div className="page-loading"><LoaderCircle className="spin" /><span>正在验证登录会话</span></div>
    if (user?.role !== 'admin') return <Navigate to="/console/apps" replace state={{ from: location }} />
    return <Outlet />
  }
  // App.tsx console 下：
  <Route element={<RequireAdmin />}>
    <Route path="agents" element={<AgentsPage />} />
    <Route path="audit" element={<AuditPage />} />
    <Route path="users" element={<UsersPage />} />
  </Route>
  ```
- **验收**：`tsc -b` 通过；OA 登录态直接访问 `/console/users` → 302 到 `/console/apps`；admin 访问不受影响。

---

## 二、P1 — 健壮性与体验（第二批）

### P1-1【Medium】AuthContext 回退逻辑简化（F-3）
- **位置**：`open-platform-web/src/auth/AuthContext.tsx:39-51`
- **问题**：仅 `ApiError && 401` 才回退 OA；网络错误/5xx 直接把 user 置 null，OA 用户被瞬时登出。
- **设计**：去掉 401 特判，任何 admin 探测失败都尝试 OA 回退（更贴合"任一有效会话"语义）：
  ```tsx
  try {
    const session = await platformApi.getSession()
    if (!active) return
    setUser({ role: 'admin', ... })
  } catch {
    // 管理员会话不可用（401/网络/5xx）→ 回退 OA；两者都失败才算未登录
    try {
      const oa = await oaApi.me()
      if (!active) return
      setUser({ role: 'oa', username: oa.itcode, name: oa.name || oa.itcode, email: oa.email })
    } catch { if (active) setUser(null) }
  } finally { if (active) setLoading(false) }
  ```
- **验收**：`tsc -b`、`vitest` 通过；手动：OA 登录后断网/后端 500 时不再跳登录页（刷新后 OA 会话仍生效）。

### P1-2【Medium】ApiPlayground 限制 baseUrl 防 Key 外泄（F-4）
- **位置**：`open-platform-web/src/pages/ApiPlaygroundPage.tsx:78,118,123`
- **问题**：`baseUrl` 可填任意主机，`Authorization: Bearer <Key>` 会发往该主机。
- **设计（推荐 A）**：**移除可编辑 baseUrl，固定同源**（`window.location.origin`）——部署本就同源托管，跨域浏览器直连受 CORS 限制本就不可用。发送逻辑去掉自定义 origin 拼接。
- **备选 B**：保留输入，但校验 `new URL(baseUrl).origin === window.location.origin`，不一致时给出醒目警告并要求二次确认（防误发）。
- **验收**：playground 请求永远发往当前站点；无自定义主机路径。

### P1-3【Medium】dev.sh 参数解析与健壮性（I-2 / I-4）
- **位置**：`dev.sh:263-265`（build 参数）、`:129`（kill -0 空 PID）、`:168-171`（dev_go 递归未排除大目录）
- **设计**：
  1. build 改为扫描参数（不再依赖固定位置 `$2`）：
  ```bash
  build)
    NO_CACHE=0; TARGET="unidata"
    for a in "$@"; do
      case "$a" in
        --no-cache) NO_CACHE=1 ;;
        unidata|go|all) TARGET="$a" ;;
        *) die "未知参数: $a（可选 unidata|go|all / --no-cache）" ;;
      esac
    done
    case "$TARGET" in ... esac
  ```
  2. `start_local_go`/`cmd_status` 的 PID 判断加 `[[ "$pid" =~ ^[0-9]+$ ]]` 守卫（先判文件存在 + 内容为数字再 `kill -0`）。
  3. `dev_go` 的 find 增加 `-path '*/node_modules' -prune -o` 与 vendor 排除。
- **验收**：`./dev.sh build --no-cache`（缺 target）正常以 `unidata` + 无缓存执行；`bash -n dev.sh` 通过；`./dev.sh go status` 无 `kill: usage` 噪音。

### P1-4【Medium】`.superpowers` 任务简报 DB host 修正（I-3）
- **位置**：`.superpowers/sdd/user-management/task-1-brief.md:20,87`
- **设计**：`DATABASE_URL` 由 `...@127.0.0.1:5432/...` 改为容器内可达的 `postgresql+asyncpg://postgres:change-me@postgres:5432/postgres`（迁移在 `unidata-migrate` 容器内执行）；`:87` 绝对本地路径改相对路径。
- **验收**：照简报操作可连上 postgres；无本机用户名/路径泄露。

### P1-5【Medium】启用用户语义文档化 + UI 提示（B-5，配合 D-3）
- **位置**：`open-platform-web/src/pages/UsersPage.tsx`（启用按钮）
- **设计**：启用确认/提示文案加"其名下应用保持禁用状态，需逐个手动启用"；`GET /users` 接口文档注明语义。不改变后端行为。
- **验收**：OA 用户被禁用→启用后，API Key 仍被拒（应用仍 disabled）为预期；页面有明确提示。

### P1-6【Low】OA 回调日志去 PII + 异常兜底（B-7 / B-8 / B-9）
- **位置**：`UniData/app/api/v1/endpoints/oa.py:64,68,56-86`
- **设计**：
  1. 日志去掉 `payload[:80]`（含 OA 个人信息），改为记录 `exc.detail` + payload 长度/哈希（如 `sha256(payload)[:12]`）用于定位。
  2. GET 双模**保留**（springboard 的 `app_login_url` 必须指向它，删了会断登录）；仅在日志侧不落 JWT。
  3. 双模回调体（`status==success` 分支）外包 try/except，`upsert_oa_user` 等 DB 异常 → `logger.exception` + 302 `/open-platform/login?oa=error`，不再 500。
- **验收**：非法 payload 日志不含 JWT 明文；DB 异常时返回 302 而非 500。

---

## 三、P2 — 低优/体验（可按需）

### P2-1【Low】OaCallbackPage `next` 校验（F-5）
- `open-platform-web/src/pages/OaCallbackPage.tsx:21`：前端对 `next` 做 `startsWith('/console')` 校验后才回传；后端 `oa_callback` 对 `next` 做 allowlist（默认仅 `/console` 前缀），双保险防 open-redirect。

### P2-2【Low】clipboard 兜底（F-6）
- `open-platform-web/src/utils/clipboard.ts:18-28`：`execCommand` 兜底改用临时 `Range` 选中 + 移除 textarea 节点的方式（避免含密钥节点滞留 DOM）。影响极小，可留记录。

### P2-3【Low/Info】vite proxy 环境化（I-5，可选）
- `open-platform-web/vite.config.ts:11-13`：proxy 目标改读 `process.env.UNIDATA_PROXY_TARGET`（默认 `http://127.0.0.1:8080`），dev.sh 可传入实际端口，消除"写死 8080"的提示噪音。

### P2-4【Info】git 历史二进制清理（需团队决策，本方案不改）
- 11MB `meilisearch-sync-service_go` 仍存在于 git 历史（`53f378f` 等 3 个 commit）。回收体积需 `git filter-repo` + force push，有协作风险；**建议**：由团队决定是否在低峰期执行，或接受现状（仅止损，不再增大）。

---

## 四、验证与回归策略

| 层 | 命令 | 时机 |
|---|---|---|
| 后端单测 | `cd UniData && TEST_PG_CONN_STRING='postgresql://postgres:<pw>@127.0.0.1:5432/unidata_test' /Users/libiao/.workbuddy/binaries/python/envs/default/bin/python -m pytest tests/ -v` | P0-1/P0-2/P0-3 后必跑；全部完成后全量 |
| 前端类型/单测 | `cd open-platform-web && npx tsc -b && npx vitest run` | 每个前端改动后 |
| e2e | `cd open-platform-web && npx playwright test`（BASE_URL=127.0.0.1:8080） | 全部合并前 |
| 部署回归 | `./dev.sh build unidata` → 容器 healthy、`/ready` 全绿；OA 登录闭环（302 `/open-platform/console` + Set-Cookie）；禁用用户 401；admin CSRF 写操作 403/201 | P0 批次后 |
| 配置回归 | `docker compose --env-file .env.docker config` 核对 env 单源 | P0-4 后 |

**提交卫生**（遵循仓库约定）：每项一个 commit，只 `git add` 本次文件；前端 `styles.css` 若与未提交 WIP 纠缠，先 `git status` 甄别或与用户确认合并提交；OA 相关后端改动与测试同 commit。

---

## 五、实施顺序与工作量预估

1. **批次 1（P0）**：P0-4（配置）→ P0-2/P0-3（后端鉴权小改）→ P0-1（测试）→ P0-5（前端守卫）。建议 1~2 小时。
2. **批次 2（P1）**：P1-1 → P1-2 → P1-3 → P1-6 → P1-4 → P1-5。建议 1 小时。
3. **批次 3（P2/决策项）**：D-1~D-3 文档/UI 落地 + P2-1~P2-4。按需。

> 每批次完成即按"验证与回归策略"执行，避免积压；P0 批次的 OA 测试将作为后续所有鉴权改动的回归防线。
