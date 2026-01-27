"""Pytest 配置和异步测试 fixtures 模块。"""
import asyncio
from typing import AsyncGenerator, Generator

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.main import app
from app.core.config import get_settings
from app.core.database import _make_async_conn_string, get_db
from app.models.testcase import Base


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """为每个测试用例创建默认事件循环的实例。"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


settings = get_settings()
TEST_DATABASE_URL = _make_async_conn_string(settings.pg_conn_string)

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
)

TestAsyncSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """创建带有表创建的测试数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """创建带有数据库会话覆盖和重定向跟随的测试客户端。"""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac

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