"""
UniData 生产者服务入口。

本模块的职责仅有两个：
1. 提供 create_app 工厂函数，组装 FastAPI 应用实例；
2. 提供 main 函数，便于通过 `python -m app.main` 或 uvicorn 命令启动服务。

所有业务逻辑都在其他模块中实现（api/core/services 等），这里不做任何业务处理。
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import text

from app.api.v1.endpoints.sdk import (
    python_sdk_available,
    validate_python_sdk_archive,
)
from app.api.v1.response import ok
from app.core.config import Settings, get_settings
from app.core.database import close_db, get_db_context
from app.core.logging import init_logging
from app.api.v1.router import include_api_routes
from app.services.agent_monitor import scan_agents_loop
from app.services.open_platform_service import publish_outbox_loop


def parse_cors_origins(value: str) -> list[str]:
    """解析 CORS Origins 配置，支持逗号分隔与通配符。"""
    if value.strip() == "*" or value.strip() == "":
        return ["*"]
    return [item.strip() for item in value.split(",") if item.strip()]


def mask_pg_conn_string(conn: str) -> str:
    """隐藏连接串中的密码信息，避免敏感信息泄露。"""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(conn)
        if "@" not in parts.netloc:
            return conn
        userinfo, hostinfo = parts.netloc.split("@", 1)
        if ":" in userinfo:
            user, _ = userinfo.split(":", 1)
            userinfo = f"{user}:***"
        return urlunsplit(
            (
                parts.scheme,
                f"{userinfo}@{hostinfo}",
                parts.path,
                parts.query,
                parts.fragment,
            )
        )
    except Exception:
        return conn


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """创建并配置 FastAPI 应用。

    - 读取配置（数据库连接、端口等）
    - 组装应用组件（中间件/路由/页面）
    - 注册生命周期钩子（启动/关闭时打印日志与释放资源）
    - 注册中间件与路由
    """
    if settings is None:
        settings = get_settings()

    # 保证在 uvicorn 直接加载 app 时也有日志输出
    init_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期钩子。

        在这里打印关键信息，便于排查环境问题，同时在应用退出时
        负责关闭数据库连接等共享资源。
        """
        validate_python_sdk_archive(settings)
        logger.info("PostgreSQL 连接: {}", mask_pg_conn_string(settings.pg_conn_string))
        logger.info("服务端口: {}", settings.server_port)

        # 启动后台健康扫描任务
        import asyncio

        stop_event = asyncio.Event()
        task = asyncio.create_task(scan_agents_loop(stop_event))
        outbox_task = asyncio.create_task(publish_outbox_loop(stop_event))

        # 应用运行期
        yield

        # 结束后台任务
        stop_event.set()
        await task
        await outbox_task

        # 应用关闭阶段：清理资源
        logger.info("正在关闭服务...")
        await close_db()
        logger.info("数据库连接已关闭")

    # 创建 FastAPI 应用实例，挂载生命周期管理器
    app = FastAPI(
        title="UniData 生产者服务",
        description="分布式搜索生产者 API 服务",
        version="0.1.0",
        lifespan=lifespan,
    )

    # 全局 CORS 配置：留空时不注册中间件（仅同源访问），显式配置后按需放开
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=parse_cors_origins(settings.cors_allow_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 挂载 API v1 的所有业务路由到统一前缀 /api/v1
    include_api_routes(app)

    # 挂载静态文件
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # 根路径返回开放平台首页
    @app.get("/", tags=["root"])
    async def root_page():
        return FileResponse("app/static/index.html")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"data": None, "message": exc.detail},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"data": None, "message": "内部服务器错误"},
        )

    # 简单的健康检查端点，方便 K8s/监控系统探测服务状态
    @app.get("/health", tags=["health"])
    async def health_check():
        return ok({"status": "healthy"})

    @app.get("/ready", tags=["health"])
    async def readiness_check():
        checks = {
            "database": False,
            "python_sdk": python_sdk_available(settings),
            "admin_session": bool(
                settings.open_platform_admin_password_hash.strip()
                and len(settings.open_platform_session_secret.strip()) >= 32
            ),
            "agent_registration": bool(settings.agent_registration_token.strip()),
        }
        try:
            async with get_db_context() as db:
                await db.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception as exc:
            logger.warning("readiness 数据库检查失败: {}", exc)

        ready = all(checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "data": {
                    "status": "ready" if ready else "not_ready",
                    "checks": checks,
                },
                "message": "ok" if ready else "服务尚未就绪",
            },
        )

    return app


# 提供一个可被 uvicorn / 测试客户端直接导入的应用实例
app = create_app()


def main():
    """开发环境下的便捷启动入口。

    通过 uvicorn.run 直接启动当前模块中的 app，并开启 reload 功能，
    方便开发调试。生产环境通常会在外部通过命令行启动 uvicorn/gunicorn。
    """
    import uvicorn

    init_logging(get_settings())
    settings = get_settings()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(settings.server_port.lstrip(":")),
        reload=True,
    )


if __name__ == "__main__":
    main()
