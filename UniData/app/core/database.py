"""数据库连接和会话管理模块。"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)

from app.core.config import get_settings

# 延迟初始化引擎
_engine: Optional[AsyncEngine] = None
_async_session_local: Optional[async_sessionmaker] = None


def _get_engine() -> AsyncEngine:
    """获取或创建异步引擎。"""
    global _engine
    if _engine is None:
        settings = get_settings()
        async_conn_string = _make_async_conn_string(settings.pg_conn_string)
        _engine = create_async_engine(
            async_conn_string,
            echo=False,
            future=True,
            pool_size=10,
            max_overflow=0,
        )
    return _engine


def _get_session_local() -> async_sessionmaker:
    """获取或创建异步会话工厂。"""
    global _async_session_local
    if _async_session_local is None:
        _async_session_local = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_local


def _make_async_conn_string(conn_string: str) -> str:
    """将 PostgreSQL 连接字符串转换为 asyncpg 兼容格式。

    - 将 postgres/postgresql scheme 转为 postgresql+asyncpg
    - 移除 asyncpg 不支持的 sslmode 查询参数
    - 兼容已经是 async 形式的连接串
    """
    if not conn_string:
        return conn_string

    conn_string = conn_string.strip()

    if conn_string.startswith("postgresql+asyncpg://"):
        rewritten = conn_string
    elif conn_string.startswith("postgres://"):
        rewritten = conn_string.replace("postgres://", "postgresql+asyncpg://", 1)
    elif conn_string.startswith("postgresql://"):
        rewritten = conn_string.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        rewritten = conn_string

    split_result = urlsplit(rewritten)
    if not split_result.query:
        return rewritten

    filtered_query = [
        (k.strip(), v)
        for k, v in parse_qsl(split_result.query, keep_blank_values=True)
        if k.strip() != "sslmode"
    ]

    sanitized_query = urlencode(filtered_query, doseq=True)
    sanitized_url = split_result._replace(query=sanitized_query)
    return urlunsplit(sanitized_url)


# 向后兼容性：暴露引擎和 AsyncSessionLocal 以便直接访问
# 这些将在首次访问时延迟初始化
class _LazyEngine:
    """引擎的延迟代理。"""

    def __getattr__(self, name):
        return getattr(_get_engine(), name)

    def __bool__(self):
        return _engine is not None


engine = _LazyEngine()


class _LazySessionLocal:
    """AsyncSessionLocal 的延迟代理。"""

    def __getattr__(self, name):
        return getattr(_get_session_local(), name)


AsyncSessionLocal = _LazySessionLocal()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话的依赖注入。"""
    async with _get_session_local()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db():
    """关闭数据库连接。"""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """数据库会话的上下文管理器。"""
    async with _get_session_local()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()