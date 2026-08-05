"""租户资源命名与事务上下文。"""
from __future__ import annotations

import hashlib
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_COLLECTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def tenant_schema(app_id: str) -> str:
    """返回不依赖 app_name 的稳定 PostgreSQL schema 名称。"""
    normalized = str(app_id).strip()
    if not normalized:
        raise ValueError("app_id 不能为空")
    return "tenant_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def index_uid(app_id: str, collection: str) -> str:
    """返回租户专属的 Meilisearch index UID。"""
    normalized_collection = str(collection).strip()
    if not _COLLECTION_PATTERN.fullmatch(normalized_collection):
        raise ValueError("collection 名称无效")
    return f"t_{hashlib.sha256(str(app_id).encode('utf-8')).hexdigest()[:16]}__{normalized_collection}"


async def set_tenant_context(db, app_id: str) -> None:
    """在当前事务设置 RLS 上下文，避免连接池状态泄漏。"""
    if not app_id:
        raise ValueError("app_id 不能为空")
    await db.execute(
        text("SELECT set_config('app.tenant_id', :app_id, true)"),
        {"app_id": app_id},
    )
    # SET LOCAL is transaction-scoped, so pooled connections cannot retain a
    # previous tenant's search path after the request commits or rolls back.
    schema = tenant_schema(app_id)
    await db.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    info = getattr(db, "info", None)
    if isinstance(info, dict):
        info["unidata.tenant_id"] = app_id


def tenant_schema_map(app_id: str) -> dict:
    """供 ORM statement 使用的动态 schema 映射。"""
    return {None: tenant_schema(app_id)}
