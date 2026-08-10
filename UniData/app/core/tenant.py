"""租户资源命名与事务上下文。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import text


_COLLECTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


@dataclass(frozen=True)
class TenantContext:
    """经过规范化的租户身份，统一承载数据库路由信息。"""

    app_id: str

    def __post_init__(self) -> None:
        normalized = str(self.app_id).strip()
        if not normalized:
            raise ValueError("app_id 不能为空")
        object.__setattr__(self, "app_id", normalized)

    @property
    def schema(self) -> str:
        return tenant_schema(self.app_id)


def tenant_schema(app_id: str) -> str:
    """返回不依赖 app_name 的稳定 PostgreSQL schema 名称。"""
    normalized = str(app_id).strip()
    if not normalized:
        raise ValueError("app_id 不能为空")
    return "tenant_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def normalize_collection_name(collection: str) -> str:
    """规范化并校验可用于 API、索引和 CDC 路由的集合名称。"""
    normalized = str(collection).strip()
    if not _COLLECTION_PATTERN.fullmatch(normalized):
        raise ValueError("collection 名称无效")
    return normalized


def index_uid(app_id: str, collection: str) -> str:
    """返回租户专属的 Meilisearch index UID。"""
    normalized_collection = normalize_collection_name(collection)
    return f"t_{hashlib.sha256(str(app_id).encode('utf-8')).hexdigest()[:16]}__{normalized_collection}"


async def set_tenant_context(db, app_id: str | TenantContext) -> None:
    """在当前事务设置 RLS 上下文，避免连接池状态泄漏。"""
    context = app_id if isinstance(app_id, TenantContext) else TenantContext(app_id)
    await db.execute(
        text("SELECT set_config('app.tenant_id', :app_id, true)"),
        {"app_id": context.app_id},
    )
    # SET LOCAL is transaction-scoped, so pooled connections cannot retain a
    # previous tenant's search path after the request commits or rolls back.
    await db.execute(text(f'SET LOCAL search_path TO "{context.schema}", public'))
    info = getattr(db, "info", None)
    if isinstance(info, dict):
        info["unidata.tenant_id"] = context.app_id


def tenant_schema_map(app_id: str | TenantContext) -> dict:
    """供 ORM statement 使用的动态 schema 映射。"""
    context = app_id if isinstance(app_id, TenantContext) else TenantContext(app_id)
    return {None: context.schema}
