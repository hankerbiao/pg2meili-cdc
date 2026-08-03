"""Pytest 配置和异步测试 fixtures 模块。"""
import os
from typing import AsyncGenerator
from urllib.parse import unquote, urlsplit

# 在导入 app 之前注入必填配置的测试默认值，避免无 .env 时 ValidationError
os.environ.setdefault("PG_CONN_STRING", "postgresql://postgres:test@127.0.0.1:5432/unidata_test")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.auth import AppIdentity, get_current_app
from app.core.database import _make_async_conn_string, get_db
from app.main import app
from app.models import Base, OpenPlatformApp


def _test_database_url() -> str:
    """返回隔离测试库地址，拒绝复用普通开发或生产数据库。"""
    configured = os.environ.get("TEST_PG_CONN_STRING", "").strip()
    if not configured:
        pytest.skip("数据库测试需要显式配置 TEST_PG_CONN_STRING")

    database_name = unquote(urlsplit(configured).path.rsplit("/", 1)[-1]).lower()
    name_parts = database_name.replace("-", "_").split("_")
    if "test" not in name_parts:
        pytest.fail("TEST_PG_CONN_STRING 的数据库名必须包含独立的 'test' 段")
    return _make_async_conn_string(configured)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """创建带有表创建的测试数据库会话。"""
    test_engine = create_async_engine(
        _test_database_url(),
        echo=False,
        future=True,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    try:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            test_app = await session.get(OpenPlatformApp, "test-app-id")
            if test_app is None:
                session.add(
                    OpenPlatformApp(
                        id="test-app-id",
                        app_name="test-app",
                        display_name="Test App",
                        owner_itcode="pytest",
                        status="active",
                        version=1,
                    )
                )
                await session.flush()
            yield session
    finally:
        await test_engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """创建带有数据库会话覆盖和鉴权覆盖的测试客户端。"""

    async def override_get_db():
        yield db_session

    async def override_get_current_app():
        return AppIdentity(
            app_id="test-app-id",
            app_name="test-app",
            scopes=["data:read", "data:write"],
            key_id="ak_test",
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_app] = override_get_current_app

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def clean_client() -> AsyncGenerator[AsyncClient, None]:
    """创建不带数据库 fixture 的测试客户端（用于健康检查）。"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac
