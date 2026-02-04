"""索引管理相关的业务服务层。"""
import time
from typing import Dict, Any, List

from app.core.config import get_settings
from app.core.kafka_manager import get_kafka_manager


class IndexService:
    """索引管理服务，负责发送索引相关的 Kafka 命令。"""

    @staticmethod
    def _send_command(index_uid: str, action: str, payload: Dict[str, Any]) -> None:
        # 统一构造并发送 Kafka 命令，避免接口层重复逻辑
        settings = get_settings()
        kafka = get_kafka_manager()
        now_ts = int(time.time())
        kafka.send_json(
            topic=settings.kafka_meili_command_topic,
            key=index_uid,
            payload={
                "version": 1,
                "command_id": f"{index_uid}:{now_ts}",
                "index_uid": index_uid,
                "action": action,
                "payload": payload,
                "ts": now_ts,
            },
        )
        kafka.flush()

    @staticmethod
    def update_index_settings(
        app_name: str,
        collection: str,
        filterable: List[str],
        sortable: List[str],
    ) -> str:
        index_uid = f"{app_name}_{collection}"
        IndexService._send_command(
            index_uid=index_uid,
            action="update_settings",
            payload={
                "filterableAttributes": filterable,
                "sortableAttributes": sortable,
            },
        )
        return index_uid

    @staticmethod
    def delete_index(app_name: str, collection: str) -> str:
        index_uid = f"{app_name}_{collection}"
        IndexService._send_command(
            index_uid=index_uid,
            action="delete_index",
            payload={},
        )
        return index_uid


index_service = IndexService()
