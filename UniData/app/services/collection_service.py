"""集合（索引）控制台业务逻辑层。"""
from __future__ import annotations

import uuid
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import set_tenant_context
from app.models.collection_settings import CollectionSettings
from app.repositories.document_repository import document_repository
from app.schemas.document import CollectionDetail, CollectionSettingsUpdate
from app.services.index_service import index_service


class CollectionService:
    """集合服务：聚合摘要、读取/保存设置，并下发到 Meilisearch。"""

    @staticmethod
    async def list_collections(
        db: AsyncSession,
        app_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CollectionDetail]:
        summaries = await document_repository.get_collection_summaries(db, app_id, limit, offset)
        settings_map = await CollectionService._load_settings_map(
            db, app_id, [s["collection"] for s in summaries]
        )
        return [CollectionService._to_detail(s, settings_map.get(s["collection"])) for s in summaries]

    @staticmethod
    async def get_collection(
        db: AsyncSession,
        app_id: str,
        collection: str,
    ) -> CollectionDetail:
        summaries = await document_repository.get_collection_summaries(db, app_id, limit=100, offset=0)
        summary = next((s for s in summaries if s["collection"] == collection), None)
        settings = await CollectionService._load_settings(db, app_id, collection)
        return CollectionService._to_detail(summary, settings)

    @staticmethod
    async def update_settings(
        db: AsyncSession,
        app_id: str,
        app_name: str,
        collection: str,
        body: CollectionSettingsUpdate,
    ) -> CollectionDetail:
        settings = await CollectionService._load_settings(db, app_id, collection)
        if settings is None:
            settings = CollectionSettings(
                id=uuid.uuid4().hex,
                app_id=app_id,
                collection=collection,
                version=1,
            )
            db.add(settings)
        settings.filterable_attributes = list(body.filterableAttributes)
        settings.sortable_attributes = list(body.sortableAttributes)
        # 扩展配置：None = 不更新该项（保持原值），显式值 = 覆盖。
        if body.searchableAttributes is not None:
            settings.searchable_attributes = list(body.searchableAttributes)
        if body.displayedAttributes is not None:
            settings.displayed_attributes = list(body.displayedAttributes)
        if body.distinctAttribute is not None:
            settings.distinct_attribute = body.distinctAttribute or None
        if body.typoToleranceEnabled is not None:
            settings.typo_tolerance_enabled = body.typoToleranceEnabled
        if body.paginationMaxTotalHits is not None:
            settings.pagination_max_total_hits = body.paginationMaxTotalHits
        if body.facetingMaxValuesPerFacet is not None:
            settings.faceting_max_values_per_facet = body.facetingMaxValuesPerFacet
        settings.version += 1
        await db.flush()
        # 下发到 Meilisearch（实际态由 Kafka 命令驱动）。Kafka 不可用时仅记录告警，
        # 不阻断「期望态」落库——控制台配置以 UniData 为准，后续可经 Kafka 补发。
        try:
            await index_service.update_index_settings_async(
                app_id=app_id,
                app_name=app_name,
                collection=collection,
                filterable=settings.filterable_attributes,
                sortable=settings.sortable_attributes,
                searchable=settings.searchable_attributes,
                displayed=settings.displayed_attributes,
                distinct_attribute=settings.distinct_attribute,
                typo_tolerance_enabled=settings.typo_tolerance_enabled,
                pagination_max_total_hits=settings.pagination_max_total_hits,
                faceting_max_values_per_facet=settings.faceting_max_values_per_facet,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "集合设置下发 Kafka 失败 app=%s collection=%s: %s", app_name, collection, exc
            )
        return await CollectionService.get_collection(db, app_id, collection)

    @staticmethod
    def _to_detail(
        summary: dict[str, Any] | None,
        settings: CollectionSettings | None,
    ) -> CollectionDetail:
        return CollectionDetail(
            collection=summary["collection"] if summary else "",
            doc_count=summary["doc_count"] if summary else 0,
            fields=summary["fields"] if summary else [],
            created_at=summary["created_at"] if summary else None,
            updated_at=summary["updated_at"] if summary else None,
            filterable_attributes=list(settings.filterable_attributes) if settings else [],
            sortable_attributes=list(settings.sortable_attributes) if settings else [],
            primary_key_field=settings.primary_key_field if settings else None,
            searchable_attributes=list(settings.searchable_attributes) if settings and settings.searchable_attributes is not None else None,
            displayed_attributes=list(settings.displayed_attributes) if settings and settings.displayed_attributes is not None else None,
            distinct_attribute=settings.distinct_attribute if settings else None,
            typo_tolerance_enabled=settings.typo_tolerance_enabled if settings else None,
            pagination_max_total_hits=settings.pagination_max_total_hits if settings else None,
            faceting_max_values_per_facet=settings.faceting_max_values_per_facet if settings else None,
        )

    @staticmethod
    async def _load_settings(
        db: AsyncSession, app_id: str, collection: str
    ) -> CollectionSettings | None:
        await set_tenant_context(db, app_id)
        stmt = select(CollectionSettings).where(
            CollectionSettings.app_id == app_id,
            CollectionSettings.collection == collection,
        )
        return (await db.execute(stmt)).scalars().first()

    @staticmethod
    async def _load_settings_map(
        db: AsyncSession, app_id: str, collections: list[str]
    ) -> dict[str, CollectionSettings]:
        if not collections:
            return {}
        await set_tenant_context(db, app_id)
        stmt = select(CollectionSettings).where(
            CollectionSettings.app_id == app_id,
            CollectionSettings.collection.in_(collections),
        )
        return {row.collection: row for row in (await db.execute(stmt)).scalars().all()}


collection_service = CollectionService()
