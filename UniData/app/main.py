"""
UniData 生产者服务入口。

本模块的职责仅有两个：
1. 提供 create_app 工厂函数，组装 FastAPI 应用实例；
2. 提供 main 函数，便于通过 `python -m app.main` 或 uvicorn 命令启动服务。

所有业务逻辑都在其他模块中实现（api/core/services 等），这里不做任何业务处理。
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, get_settings
from app.core.database import close_db
from app.api.v1.router import api_router


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """创建并配置 FastAPI 应用。

    - 读取配置（数据库连接、端口等）
    - 配置全局日志格式
    - 注册生命周期钩子（启动/关闭时打印日志与释放资源）
    - 注册中间件与路由
    """
    if settings is None:
        settings = get_settings()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期钩子。

        在这里打印关键信息，便于排查环境问题，同时在应用退出时
        负责关闭数据库连接等共享资源。
        """
        logger.info(f"PostgreSQL 连接: {settings.pg_conn_string}")
        logger.info(f"服务端口: {settings.server_port}")

        # 应用运行期
        yield

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

    # 全局 CORS 配置：
    # 当前放开所有来源，方便本地及多环境联调，生产环境可以按需收紧
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 挂载 API v1 的所有业务路由到统一前缀 /api/v1
    app.include_router(api_router, prefix="/api/v1")

    project_root = Path(__file__).resolve().parents[2]
    libs_dir = project_root / "libs"
    if libs_dir.exists():
        app.mount("/libs", StaticFiles(directory=libs_dir), name="libs")

    @app.get("/app/register", include_in_schema=False)
    async def app_register_page():
        html_path = project_root / "app_token_register.html"
        return FileResponse(html_path)

    @app.get("/app/review", include_in_schema=False)
    async def app_review_page():
        html_path = project_root / "app_token_review.html"
        return FileResponse(html_path)

    # 简单的健康检查端点，方便 K8s/监控系统探测服务状态
    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "healthy"}

    return app


# 提供一个可被 uvicorn / 测试客户端直接导入的应用实例
app = create_app()


def main():
    """开发环境下的便捷启动入口。

    通过 uvicorn.run 直接启动当前模块中的 app，并开启 reload 功能，
    方便开发调试。生产环境通常会在外部通过命令行启动 uvicorn/gunicorn。
    """
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(settings.server_port.lstrip(":")),
        reload=True,
    )


if __name__ == "__main__":
    main()
