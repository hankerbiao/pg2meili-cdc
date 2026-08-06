# 评审发现与处理状态（2026-08-05 变更窗口）

> 来源：2026-08-04~05 的 24h 变更评审（原 `docs/code-review-2026-08-05.md`，已并入本文）。
> 原评审规模：57 文件、16 commit（`8964d21`→`ddaa804`），0 Blocker / 2 High / 11 Medium / 6 Low。
> **结论**：未发现数据泄露级漏洞；`/audit-logs`、`/agents`、`/users` 后端均强制 admin。
> 本文记录各项**当前处理状态**——多数 P0 已随后续提交落地，剩余项待确认/排期。

## 一、已修复（已在代码中验证）

| 编号 | 问题 | 落地证据 |
|---|---|---|
| I-1 / P0-4 | compose `environment` 覆盖 `env_file` 致 `.env.docker` 应用配置静默失效 | `docker-compose.yml` 锚点仅留内部地址变量；`dev.sh` 用 `docker compose --env-file .env.docker`；`.env.docker` 现为本源 |
| B-2 / P0-2 | OA 禁用用户在 `/oa/me` 未被拦截 | `any_auth.py` `get_any_session` 经 `assert_oa_user_active(db, oa.itcode)` 拦截禁用用户（返回 401） |
| B-3 / P0-3 | admin cookie 失效时永久锁死 OA 用户 | `any_auth.py:58-61` admin 解码失败 `except` 后置 `admin=None` 并回退 OA 分支 |
| F-1 / P0-5 | admin-only 路由缺守卫（纵深防御） | `open-platform-web/src/App.tsx` `RequireAdmin` 守卫包裹 `agents`/`audit`/`users` 路由 |
| B-1 / P0-1 | OA 安全模型零自动化测试 | `UniData/tests/test_oa_security.py` 已覆盖 owner 隔离、跨 owner 403、禁用 401、OA 写免 CSRF |
| P1-2 | ApiPlayground `baseUrl` 用户可控致 Key 外泄 | `ApiPlaygroundPage.tsx:71` `baseUrl = window.location.origin`（固定同源） |
| D-2 | SameSite=Strict 对跨端口 SPA 的影响 | 维持 Strict（同站部署下 `localhost:8080` 正常）；文档见 `docs/nginx-http-domain-setup.md` |

> 原评审中"前端越权 Blocker"经亲验降级为 Medium（后端已拦数据），"OA 写缺 CSRF"为误报（`require_any_csrf` 对 OA 显式豁免）——均已确认无误。

## 二、待确认 / 未明确（未在代码中核实）

| 编号 | 问题 | 备注 |
|---|---|---|
| P1-1 | `AuthContext` 仅 401 才回退 OA，网络/5xx 会瞬时登出 OA 用户 | 需读 `auth/AuthContext.tsx` 确认是否已改为"任何 admin 探测失败都回退" |
| P1-3 | `dev.sh build` 参数解析（`--no-cache` 需显式 target 后才生效）与健壮性 | 现有 `build_unidata` 读 `NO_CACHE`；参数扫描是否解耦待核 |
| P1-4 | `.superpowers` 任务简报 DB host 写死 `127.0.0.1`（应为 `postgres`） | 属 `.superpowers` 文档，不阻塞运行，建议修正 |
| P1-5 | 重新启用用户"不复活应用"缺 UI 提示 | `D-3` 维持语义；`UsersPage` 启用按钮旁是否加 hint 待确认 |
| P1-6 | OA 回调日志泄露 JWT/PII、缺异常兜底 | `oa.py` 回调体是否包 try/except、日志去 payload 待核 |
| P2-1 | `OaCallbackPage` `next` 参数校验防 open-redirect | 低优，前后端双校验 |
| P2-2 | clipboard 兜底 textarea 短暂入 DOM | 影响极小（HTTPS 走 `navigator.clipboard`） |
| P2-3 | vite proxy 目标环境化 | `vite.config.ts` 目前写死 `8080`，与容器一致，仅灵活性低 |
| P2-4 | git 历史中 11MB 二进制 `meilisearch-sync-service_go` | 需团队决策 `git filter-repo` + force push；仅止损不再增大，详见 `CLAUDE.md`/项目记忆 |

## 三、决策项（已拍板）

- **D-1 owner 语义**：全员强制 `owner_itcode = 登录人`（admin 也不代建他人应用）；仅修正文档，不改代码。项目记忆中"admin 可填 owner"描述已过时。
- **D-2 SameSite**：保持 `Strict`，文档化"前端与 API 同站部署"约束。
- **D-3 启用用户**：保持"不自动复活应用"，加 UI 提示（语义不变）。

## 四、验证与回归（持续有效）

| 层 | 命令 |
|---|---|
| 后端单测 | `cd UniData && TEST_PG_CONN_STRING=... pytest tests/ -v` |
| 前端类型/单测 | `cd open-platform-web && npx tsc -b && npx vitest run` |
| e2e | `cd open-platform-web && npx playwright test`（BASE_URL=127.0.0.1:8080） |
| 部署回归 | `./dev.sh build unidata` → 容器 healthy、`/ready` 全绿；OA 登录闭环 + Set-Cookie；禁用用户 401；admin CSRF 写操作 403/201 |
| 配置回归 | `docker compose --env-file .env.docker config` 核对 env 单源 |

提交卫生：每项一个 commit，只 `git add` 本次文件；OA 相关后端改动与测试同 commit。
