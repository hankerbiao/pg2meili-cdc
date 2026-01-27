"""
UniData 生产者服务

基于 FastAPI 的分布式搜索生产者服务。
从 Go 实现重构而来。
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.database import close_db
from app.api.v1.router import api_router


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(f"PostgreSQL 连接: {settings.pg_conn_string}")
        logger.info(f"服务端口: {settings.server_port}")

        yield

        logger.info("正在关闭服务...")
        await close_db()
        logger.info("数据库连接已关闭")

    app = FastAPI(
        title="UniData 生产者服务",
        description="分布式搜索生产者 API 服务",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "healthy"}

    return app


app = create_app()


def main():
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