# UniData 域名绑定改动方案（HTTP，不走 HTTPS）

> 目标：将域名（占位 `your-domain.com`）通过 nginx 80 端口反向代理到 UniData 服务。
> 约束：**不启用 HTTPS**，全程 HTTP。执行者按本文档逐步执行，每步都需验证后再进入下一步。
> 文档编写时间：2026-08-04。涉及文件若与此后仓库状态不一致，以仓库实际内容为准并报告差异。

---

## 0. 背景与目标

- UniData（FastAPI 服务）通过 docker-compose 部署，**容器内监听 8080**。
- 宿主映射端口在 `.env.docker` 中配置为 `UNIDATA_PORT=8080`，即**宿主机 `127.0.0.1:8080` 可达服务**。
- 前端静态资源由 UniData 自身托管（`open_platform_dist_dir`），因此 **nginx 只需反代 UniData 一个上游**，无需额外静态目录。
- 本次改动：nginx 监听 80，将 `your-domain.com` 的请求转发到 `http://127.0.0.1:8080`。

---

## 1. 现状与关键事实（执行前必读）

| 事实 | 值 | 来源 |
|---|---|---|
| UniData 容器内端口 | `8080` | `docker-compose.yml` unidata 服务 `ports: "${UNIDATA_PORT:-8080}:8080"` |
| UniData 宿主端口 | `8080` | `.env.docker` → `UNIDATA_PORT=8080` |
| 健康检查端点 | `GET /ready`（容器内 127.0.0.1:8080） | `docker-compose.yml` unidata healthcheck |
| Cookie 安全标志 | `OPEN_PLATFORM_COOKIE_SECURE=false` | `.env.docker`；**HTTP 场景必须保持 false，禁止改为 true**（HTTPS 下浏览器才会发送 Secure Cookie） |
| CORS 默认值 | `http://localhost:8080` | `docker-compose.yml` `x-unidata-environment` 锚点 |
| CORS 实际生效来源 | 根目录 `.env` 或 shell 环境 | 见下方"陷阱" |

### ⚠️ 陷阱 1：CORS 修改必须改根目录 `.env`，改 `.env.docker` 无效

`docker-compose.yml` 中 unidata 服务的配置同时使用了：

```yaml
env_file:
  - path: ./.env.docker        # ① 文件注入
environment:
  <<: *unidata-environment     # ② 锚点，含 CORS_ALLOW_ORIGINS: ${CORS_ALLOW_ORIGINS:-http://localhost:8080}
```

docker-compose 变量优先级：**`environment:` 覆盖 `env_file:`**。
而 `${CORS_ALLOW_ORIGINS:-...}` 的插值来源是 **shell 环境或根目录 `.env`**（compose 项目 env），不是 `.env.docker`。

结论：
- 只在 `.env.docker` 里改 `CORS_ALLOW_ORIGINS` → **不生效**（会被 environment 块覆盖）。
- 正确做法：在**根目录 `.env`** 添加 `CORS_ALLOW_ORIGINS=...`，或直接改 `docker-compose.yml` 锚点默认值。

### ⚠️ 陷阱 2：Cookie

`OPEN_PLATFORM_COOKIE_SECURE` 保持 `false`。若误改为 `true`，HTTP 下浏览器不发送 Cookie，开放平台管理员登录会失效。

### ⚠️ 陷阱 3：git 提交卫生

仓库 main 分支常有他人未提交的 WIP（docker、README 等）。**本次改动若涉及 git 提交，只能 `git add` 本次修改的文件**，禁止 `git add -A` / `git add .`。

---

## 2. 前置确认（第一步，收集信息）

执行以下命令并核对，**任一失败必须停下并向用户报告**：

```bash
# 2.1 确认域名 DNS 已解析到本机公网 IP
dig +short your-domain.com

# 2.2 确认 nginx 已安装及部署方式（conf.d 或 sites-available，二选一）
nginx -v
ls -d /etc/nginx/conf.d 2>/dev/null && echo "CONFD"
ls -d /etc/nginx/sites-available 2>/dev/null && echo "SITES_AVAILABLE"

# 2.3 确认 8080 端口在监听（容器映射）
ss -tlnp | grep 8080 || lsof -i :8080

# 2.4 确认 UniData 宿主健康检查通过
curl -i http://127.0.0.1:8080/ready
# 预期：HTTP/1.1 200 OK

# 2.5 检查 80 端口是否已被其他站点占用（避免 server_name 冲突）
grep -rn "listen 80" /etc/nginx/conf.d/ /etc/nginx/sites-enabled/ 2>/dev/null || true

# 2.6 确认防火墙/安全组放行 80 端口（对外部可访问性至关重要）
# Debian/Ubuntu: sudo ufw status ；CentOS: sudo firewall-cmd --list-ports ；云厂商看安全组控制台
```

记录实际采用的 nginx 配置目录（conf.d 或 sites-available），后续步骤以实际为准。

---

## 3. 改动步骤

### Step 1：新增 nginx 站点配置

在确认的 nginx 配置目录下新建文件：

- conf.d 方式：`/etc/nginx/conf.d/unidata-your-domain.conf`
- sites-available 方式：`/etc/nginx/sites-available/unidata-your-domain`，并执行
  `sudo ln -s /etc/nginx/sites-available/unidata-your-domain /etc/nginx/sites-enabled/`

文件内容（**将 `your-domain.com` 全部替换为真实域名**）：

```nginx
# UniData HTTP 反向代理（80 -> 127.0.0.1:8080）
# 注意：本配置不含 TLS；若域名 DNS 未解析到本机，server_name 匹配将失效。
upstream unidata_backend {
    server 127.0.0.1:8080;
    keepalive 32;
}

server {
    listen 80;
    server_name your-domain.com;

    # 文档上传/批量接口，按需调整（单位 m）
    client_max_body_size 100m;

    location / {
        proxy_pass http://unidata_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # keepalive 模式下必须置空 Connection，否则上游连接无法复用
        proxy_set_header Connection "";

        proxy_connect_timeout 30s;
        proxy_read_timeout 300s;   # 长任务/批量接口
        proxy_send_timeout 300s;

        # 文件上传/流式响应更稳（可选，不影响功能）
        proxy_buffering off;
    }
}
```

说明：
- UniData 无 WebSocket 端点（已确认），**无需** `Upgrade`/`Connection: upgrade` 头转发。
- `/ready`、`/health`、`/docs` 等路径均由 UniData 提供，统一走 `/` 反代即可。
- 若服务器上已有其他 80 端口站点，保留各自 `server_name`，互不影响。

### Step 2：校验并重载 nginx

```bash
sudo nginx -t
# 预期输出两行均为 ... ok / successful

sudo nginx -s reload
# 无输出即成功
```

### Step 3：修改 CORS（关键，见陷阱 1）

在**根目录** `/path/to/pg2meili-cdc/.env`（仓库根目录，与 docker-compose.yml 同级）追加一行（保留原有 `MEILI_API_KEY`，只追加不删除）：

```bash
# 追加到 .env 末尾（逗号分隔，原 localhost:8080 等开发源务必保留，避免影响本地联调）
CORS_ALLOW_ORIGINS=http://your-domain.com,http://localhost:8080,http://127.0.0.1:8080
```

> 若根目录 `.env` 已存在 `CORS_ALLOW_ORIGINS` 行，直接替换该行的值。
> **禁止只改 `.env.docker` 中的 CORS_ALLOW_ORIGINS（无效）。**

### Step 4：重建并重启 unidata 容器（使 CORS 生效）

```bash
cd /path/to/pg2meili-cdc
docker compose up -d unidata
# 预期：unidata 容器重建并启动
```

等待健康检查通过（约 10~40s）：

```bash
docker compose ps unidata
# 预期：STATUS 列为 healthy
```

### Step 5：验证

```bash
# 5.1 直连宿主端口（应先于域名验证）
curl -i http://127.0.0.1:8080/ready
# 预期：200 OK

# 5.2 通过 nginx 转发（带 Host 头，模拟域名访问）
curl -i -H "Host: your-domain.com" http://127.0.0.1/ready
# 预期：200 OK，且响应头含 X-Forwarded-For / X-Forwarded-Proto 效果正常

# 5.3 真实域名访问
curl -i http://your-domain.com/ready
# 预期：200 OK

# 5.4 CORS 预检（从域名发起的跨域 OPTIONS，按实际前端调用场景调整 Origin）
curl -i -X OPTIONS http://your-domain.com/ -H "Origin: http://your-domain.com" -H "Access-Control-Request-Method: GET"
# 预期：响应头包含 Access-Control-Allow-Origin: http://your-domain.com

# 5.5 容器内确认环境变量已生效
docker compose exec unidata sh -c 'echo $CORS_ALLOW_ORIGINS'
# 预期：输出包含 http://your-domain.com
```

浏览器最终验收（人工）：
1. 访问 `http://your-domain.com/` 能打开开放平台登录页。
2. 使用管理员账号登录成功（若登录失败，先检查 `OPEN_PLATFORM_COOKIE_SECURE` 是否被误改为 true）。
3. 在已打开页面执行一次文档检索/上传类操作，确认接口正常（间接验证 CORS 与请求体大小限制）。

---

## 4. 回滚方案

任一验证失败时，按对应步骤回滚：

```bash
# 回滚 nginx：删除站点配置并重载
sudo rm -f /etc/nginx/conf.d/unidata-your-domain.conf
# （sites-available 方式还需：sudo rm -f /etc/nginx/sites-enabled/unidata-your-domain）
sudo nginx -t && sudo nginx -s reload

# 回滚 CORS：删除根目录 .env 中的 CORS_ALLOW_ORIGINS 行，并重建容器
# （编辑 /path/to/pg2meili-cdc/.env 删除该行）
cd /path/to/pg2meili-cdc && docker compose up -d unidata
```

---

## 5. 注意事项汇总

1. **Cookie**：`OPEN_PLATFORM_COOKIE_SECURE` 保持 `false`，勿改。
2. **CORS**：改根目录 `.env` 或 `docker-compose.yml` 锚点，勿只改 `.env.docker`；保留原有 localhost 开发源。
3. **端口绑定（可选加固）**：docker-compose 头部注释建议生产环境将宿主端口绑定恢复为仅本机。可选改动：`docker-compose.yml` 中 unidata 端口映射 `"${UNIDATA_PORT:-8080}:8080"` → `"127.0.0.1:${UNIDATA_PORT:-8080}:8080"`，使局域网无法绕过 nginx 直连 8080。执行前需确认没有其他客户端依赖直接访问 8080。
4. **git**：若需要提交改动，只 `git add` 本次修改的文件（nginx 配置通常在仓库外，无需提交；仓库内改动为 `.env` 与可能的 `docker-compose.yml`）。`.env`/`.env.docker` 含密钥，确认是否被 .gitignore 忽略，避免误提交。
5. **80 端口**：云服务器需在安全组放行 80（TCP），否则外部无法访问。
6. 执行过程中所有命令输出与预期不符时，**停止并报告**，不要自行绕过。
