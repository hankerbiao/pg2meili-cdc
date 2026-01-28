"""数据库连接和会话管理模块。

统一封装：
1. AsyncEngine 的创建与连接串转换；
2. AsyncSession 的获取与事务提交/回滚；
3. 提供 get_db 依赖函数供 FastAPI 注入使用。

上层代码不直接操作引擎和 sessionmaker，而是通过本模块暴露的接口访问数据库。
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

# 延迟初始化引擎与会话工厂，避免在模块导入阶段就连接数据库
_engine: Optional[AsyncEngine] = None
_async_session_local: Optional[async_sessionmaker] = None


def _get_engine() -> AsyncEngine:
    """获取或创建异步引擎。

    使用配置中的 pg_conn_string 创建 asyncpg 驱动的 SQLAlchemy AsyncEngine，
    并设置连接池大小等参数。只在首次调用时真正创建。
    """
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
    """获取或创建异步会话工厂。

    通过 async_sessionmaker 统一生成 AsyncSession，禁用自动提交与自动 flush，
    以方便在 get_db 中显式控制事务生命周期。
    """
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

    主要做三件事：
    1. 将 postgres/postgresql scheme 转为 postgresql+asyncpg；
    2. 过滤掉 asyncpg 不支持的 sslmode 等参数；
    3. 对已经是 async 形式的连接串保持原样返回。
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
    """引擎的延迟代理。

    通过 __getattr__ 在第一次访问时创建真正的 AsyncEngine，之后复用。
    """

    def __getattr__(self, name):
        return getattr(_get_engine(), name)

    def __bool__(self):
        return _engine is not None


engine = _LazyEngine()


class _LazySessionLocal:
    """AsyncSessionLocal 的延迟代理。

    用与 _LazyEngine 类似的方式延迟创建 sessionmaker。
    """

    def __getattr__(self, name):
        return getattr(_get_session_local(), name)


AsyncSessionLocal = _LazySessionLocal()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话的依赖注入。

    用于 FastAPI 的 Depends，保证：
    - 每个请求使用一个独立的 AsyncSession；
    - 正常结束时自动 commit；
    - 发生异常时自动 rollback；
    - 最后无论成功失败都 close。
    """
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
    """关闭数据库连接。

    在应用退出时调用，安全地释放连接池资源。
    """
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """数据库会话的上下文管理器。

    用于脚本或后台任务中手动控制数据库生命周期，与 get_db 类似，
    但不依赖 FastAPI 的依赖注入机制。
    """
    async with _get_session_local()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
