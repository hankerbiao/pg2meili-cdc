"""索引管理相关的业务服务层。"""
import asyncio
import time
from typing import Dict, Any, List

from app.core.config import get_settings
from app.core.kafka_manager import get_kafka_manager
from app.core.tenant import index_uid as tenant_index_uid


class IndexService:
    """索引管理服务，负责发送索引相关的 Kafka 命令。"""

    @staticmethod
    def _send_command(
        app_id: str,
        app_name: str,
        collection: str,
        action: str,
        payload: Dict[str, Any],
    ) -> str:
        # 统一构造并发送 Kafka 命令，避免接口层重复逻辑
        resolved_index_uid = tenant_index_uid(app_id, collection)
        settings = get_settings()
        kafka = get_kafka_manager()
        now_ts = int(time.time())
        kafka.send_json(
            topic=settings.kafka_meili_command_topic,
            key=resolved_index_uid,
            payload={
                "version": 2,
                "command_id": f"{resolved_index_uid}:{now_ts}",
                "app_id": app_id,
                "collection": collection,
                "index_uid": resolved_index_uid,
                "action": action,
                "payload": payload,
                "ts": now_ts,
            },
        )
        kafka.flush()
        return resolved_index_uid

    @staticmethod
    def update_index_settings(
        app_id: str,
        app_name: str,
        collection: str,
        filterable: List[str],
        sortable: List[str],
        searchable: Any | None = None,
        displayed: Any | None = None,
        distinct_attribute: str | None = None,
        typo_tolerance_enabled: bool | None = None,
        pagination_max_total_hits: int | None = None,
        faceting_max_values_per_facet: int | None = None,
    ) -> str:
        # 扩展配置项为 None 时不下发，避免覆盖 Meilisearch 的默认/现状设置。
        payload: Dict[str, Any] = {
            "filterableAttributes": list(filterable),
            "sortableAttributes": list(sortable),
        }
        if searchable is not None:
            payload["searchableAttributes"] = list(searchable)
        if displayed is not None:
            payload["displayedAttributes"] = list(displayed)
        if distinct_attribute is not None:
            payload["distinctAttribute"] = distinct_attribute
        if typo_tolerance_enabled is not None:
            payload["typoToleranceEnabled"] = typo_tolerance_enabled
        if pagination_max_total_hits is not None:
            payload["paginationMaxTotalHits"] = pagination_max_total_hits
        if faceting_max_values_per_facet is not None:
            payload["facetingMaxValuesPerFacet"] = faceting_max_values_per_facet
        return IndexService._send_command(
            app_id=app_id,
            app_name=app_name,
            collection=collection,
            action="update_settings",
            payload=payload,
        )

    @staticmethod
    def delete_index(app_id: str, app_name: str, collection: str) -> str:
        return IndexService._send_command(
            app_id=app_id,
            app_name=app_name,
            collection=collection,
            action="delete_index",
            payload={},
        )

    async def update_index_settings_async(self, **kwargs: Any) -> str:
        """在线程池执行同步 Kafka 客户端，避免阻塞 FastAPI 事件循环。"""
        return await asyncio.to_thread(self.update_index_settings, **kwargs)

    async def delete_index_async(self, **kwargs: Any) -> str:
        """在线程池执行同步 Kafka 客户端，避免阻塞 FastAPI 事件循环。"""
        return await asyncio.to_thread(self.delete_index, **kwargs)


index_service = IndexService()
