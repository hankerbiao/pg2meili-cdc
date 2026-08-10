# UniData 域名绑定（HTTP 反向代理）

> 目标：把 API 域名（占位 `your-domain.com`）经 nginx 80 端口反代到 UniData 服务。开放平台前端需单独部署，并将 `/open-platform/` 代理到前端站点。
> 约束：**不启用 HTTPS**，全程 HTTP。本文档为操作步骤，若与仓库实际状态冲突，以仓库为准并报告差异。

## 1. 关键事实（执行前必读）

| 事实 | 值 | 来源 |
|---|---|---|
| UniData 容器内端口 | `8080` | `docker-compose.yml` `ports: "${UNIDATA_PORT:-8080}:8080"` |
| UniData 宿主端口 | `8080` | `.env.docker` → `UNIDATA_PORT=8080` |
| 健康检查 | `GET /ready` | `docker-compose.yml` unidata healthcheck |
| Cookie Secure | `OPEN_PLATFORM_COOKIE_SECURE=false` | `.env.docker`；**HTTP 下必须保持 false**，改 true 会导致浏览器不发送 Cookie、登录失效 |

### CORS / 环境变量来源（已统一）

应用配置（含 `CORS_ALLOW_ORIGINS`、`PG_CONN_STRING`、`LOG_*`、`KAFKA_*`、各类密钥）**统一由 `.env.docker` 注入**：

- `docker-compose.yml` 的 `x-unidata-environment` 锚点只保留 Docker 内部地址类变量（`SERVER_PORT`、`KAFKA_BOOTSTRAP_SERVERS`、`REDIS_URL` 等），不再放应用配置。
- `dev.sh` 以 `docker compose --env-file .env.docker` 运行，变量插值源与 `.env.docker` 一致。

> 旧文档的「陷阱 1：改 `.env.docker` 无效」**已过时**——现在恰恰相反：CORS 等应用配置**直接改 `.env.docker`** 即可生效，根目录 `.env` 不再是这些键的来源。

### 其它约束

- **Cookie 安全**：`OPEN_PLATFORM_COOKIE_SECURE` 保持 `false`，勿改（HTTP 下浏览器才会发送 Cookie）。
- **SameSite**：管理员与 OA 会话 Cookie 均为 `SameSite=Strict`。Strict 只认 scheme+可注册域名、不看端口；前端与 API 必须使用同一 scheme 和可注册域名（例如都挂在 `your-domain.com` 下），否则登录 Cookie 不会携带。
- **git 卫生**：main 常有他人未提交 WIP。涉及 git 提交时只 `git add` 本次文件，禁止 `git add -A` / `git add .`；`.env` / `.env.docker` 含密钥，确认被 `.gitignore` 忽略再提交。

## 2. 前置确认

```bash
# 2.1 域名 DNS 已解析到本机公网 IP
dig +short your-domain.com

# 2.2 nginx 已安装及配置目录（conf.d 或 sites-available）
nginx -v
ls -d /etc/nginx/conf.d 2>/dev/null && echo "CONFD"
ls -d /etc/nginx/sites-available 2>/dev/null && echo "SITES_AVAILABLE"

# 2.3 8080 在监听（容器映射）
ss -tlnp | grep 8080 || lsof -i :8080

# 2.4 UniData 健康检查
curl -i http://127.0.0.1:8080/ready   # 预期 200 OK

# 2.5 80 端口是否已被占用（避免 server_name 冲突）
grep -rn "listen 80" /etc/nginx/conf.d/ /etc/nginx/sites-enabled/ 2>/dev/null || true

# 2.6 防火墙/安全组放行 80（外部可访问前提）
```

## 3. 操作步骤

### Step 1：新增 nginx 站点配置

conf.d 方式：`/etc/nginx/conf.d/unidata-your-domain.conf`
sites-available 方式：`/etc/nginx/sites-available/unidata-your-domain`，并 `sudo ln -s ... /etc/nginx/sites-enabled/`

将 `your-domain.com` 替换为真实域名：

```nginx
upstream unidata_backend {
    server 127.0.0.1:8080;
    keepalive 32;
}

upstream open_platform_frontend {
    server 127.0.0.1:4173;
    keepalive 16;
}

server {
    listen 80;
    server_name your-domain.com;
    client_max_body_size 100m;

    # API 和 SDK 下载转发到 UniData
    location /api/ {
        proxy_pass http://unidata_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";          # keepalive 复用需置空
        proxy_connect_timeout 30s;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_buffering off;
    }

    location = /health { proxy_pass http://unidata_backend; }
    location = /ready { proxy_pass http://unidata_backend; }
    location = /docs { proxy_pass http://unidata_backend; }

    # 独立部署的 open-platform-web（示例前端上游）
    location /open-platform/ {
        proxy_pass http://open_platform_frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

在 `upstream` 区域增加前端上游（例如 `server 127.0.0.1:4173;`，按实际部署端口调整）。前端构建时使用仓库既定的 `/open-platform` basename，并配置 SPA fallback。UniData 无 WebSocket 端点，无需 `Upgrade` 头转发。

### Step 2：校验并重载

```bash
sudo nginx -t          # 两行 ok / successful
sudo nginx -s reload   # 无输出即成功
```

### Step 3：配置 CORS（改 `.env.docker`）

编辑仓库根目录 `.env.docker`，在 `CORS_ALLOW_ORIGINS` 追加域名（保留原有 `localhost`/`127.0.0.1` 开发源）：

```bash
CORS_ALLOW_ORIGINS=http://your-domain.com,http://localhost:8080,http://127.0.0.1:8080
```

然后重建 unidata 容器使配置生效：

```bash
cd /path/to/pg2meili-cdc
docker compose up -d unidata
docker compose ps unidata     # STATUS = healthy
```

### Step 4：验证

```bash
curl -i http://127.0.0.1:8080/ready                                   # 200 OK
curl -i -H "Host: your-domain.com" http://127.0.0.1/ready             # 200 OK
curl -i http://your-domain.com/ready                                  # 200 OK
curl -i -X OPTIONS http://your-domain.com/ \
  -H "Origin: http://your-domain.com" -H "Access-Control-Request-Method: GET"
  # 响应头含 Access-Control-Allow-Origin: http://your-domain.com
docker compose exec unidata sh -c 'echo $CORS_ALLOW_ORIGINS'          # 含 your-domain.com
```

浏览器验收：访问 `http://your-domain.com/open-platform/` 能打开登录页；管理员登录成功；执行一次检索/上传确认接口正常。

## 4. 回滚

```bash
sudo rm -f /etc/nginx/conf.d/unidata-your-domain.conf
# sites-available 方式还需：sudo rm -f /etc/nginx/sites-enabled/unidata-your-domain
sudo nginx -t && sudo nginx -s reload
# 回滚 CORS：编辑 .env.docker 删去域名后 docker compose up -d unidata
```

## 5. 注意事项

1. `OPEN_PLATFORM_COOKIE_SECURE` 保持 `false`。
2. CORS 等应用配置改 `.env.docker`（不再是根目录 `.env`）；保留原有 localhost 开发源。
3. 可选加固：生产把宿主端口绑定改 `127.0.0.1:${UNIDATA_PORT:-8080}:8080`，使局域网无法绕过 nginx 直连 8080（需确认无其他客户端依赖直连）。
4. 云服务器安全组放行 80（TCP）。
5. 命令输出与预期不符时**停止并报告**，不要自行绕过。
