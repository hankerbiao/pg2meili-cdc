# UniData 服务部署

UniData 是基于 FastAPI 的异地分布式搜索“生产端”服务，负责将业务数据标准化写入 PostgreSQL。

## 1. 环境要求

- **Python**: >= 3.11
- **数据库**: PostgreSQL 14+ (需开启 WAL logical decoding)
- **依赖管理**: 推荐使用 [uv](https://github.com/astral-sh/uv) 或 pip

## 2. 配置说明

配置通过环境变量或 `.env` 文件加载，核心定义在 `app/core/config.py`。

### 核心配置项

| 变量名 | 说明 | 示例值 |
| :--- | :--- | :--- |
| `PG_CONN_STRING` | PostgreSQL 连接串 | `postgres://user:pass@host:5432/unidata` |
| `SERVER_PORT` | 服务监听端口 | `8080` |
| `JWT_SECRET` | JWT 签名秘钥 (HS256) | `your-secret-key` |
| `MEILI_DEFAULT_URL` | Meilisearch 地址 | `http://localhost:7700` |
| `MEILI_DEFAULT_API_KEY` | Meilisearch 密钥 | `my_master_key` |

## 3. 部署步骤

### 3.1 获取代码

```bash
git clone https://github.com/hankerbiao/pg2meili-cdc.git
cd pg2meili-cdc/UniData
```

### 3.2 安装依赖与运行 (推荐使用 uv)

我们推荐使用 `uv` 来管理虚拟环境，速度更快且更稳定。

```bash
# 1. 创建虚拟环境
uv venv

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 安装依赖
uv pip install -e .
```

### 3.3 启动服务

```bash
# 直接启动
python main.py

# 或者使用 uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

服务启动后，默认监听 `http://0.0.0.0:8080`。

## 4. 验证部署

### 健康检查

访问 `/health` 接口确认服务状态：

```bash
curl http://localhost:8080/health
# 返回: {"status": "healthy"}
```

### 接口文档

在浏览器访问 Swagger UI 进行交互式测试：

- 地址: `http://localhost:8080/docs`
