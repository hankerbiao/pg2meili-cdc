"""Kafka 管理器：统一管理 Kafka Producer 与发送行为。

设计目标：
- 高可扩展：配置集中、序列化可替换、支持 headers/key/partition。
- 高可读性：API 简洁、职责清晰。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional

from kafka import KafkaProducer

from functools import lru_cache

from app.core.config import get_settings


# 定义序列化函数类型：接收任意对象，返回字节串
Serializer = Callable[[Any], bytes]


def _default_json_serializer(value: Any) -> bytes:
    """默认的 JSON 序列化器。
    
    特点：
    - 不转义非 ASCII 字符（中文友好）。
    - 去除分隔符后的空格（节省流量）。
    - 最终编码为 UTF-8 字节串。
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class KafkaProducerConfig:
    """Kafka 生产者配置类（不可变数据类）。
    
    属性对应 kafka-python 的 KafkaProducer 参数。
    使用 frozen=True 防止配置在运行时被意外修改。
    """
    bootstrap_servers: str
    client_id: str
    security_protocol: str
    sasl_mechanism: Optional[str]
    sasl_username: Optional[str]
    sasl_password: Optional[str]
    acks: str
    retries: int
    linger_ms: int
    batch_size: int
    request_timeout_ms: int

    @staticmethod
    def from_settings() -> "KafkaProducerConfig":
        """工厂方法：从全局 Settings 创建配置实例。"""
        settings = get_settings()
        return KafkaProducerConfig(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            client_id=settings.kafka_client_id,
            security_protocol=settings.kafka_security_protocol,
            sasl_mechanism=settings.kafka_sasl_mechanism,
            sasl_username=settings.kafka_sasl_username,
            sasl_password=settings.kafka_sasl_password,
            acks=settings.kafka_acks,
            retries=settings.kafka_retries,
            linger_ms=settings.kafka_linger_ms,
            batch_size=settings.kafka_batch_size,
            request_timeout_ms=settings.kafka_request_timeout_ms,
        )


class KafkaManager:
    """Kafka Producer 管理器。
    
    封装了 KafkaProducer 的初始化和消息发送逻辑，
    提供了更友好的 API，特别是针对 JSON 数据的发送。
    """

    def __init__(
        self,
        config: KafkaProducerConfig,
        value_serializer: Optional[Serializer] = None,
        key_serializer: Optional[Serializer] = None,
    ) -> None:
        """初始化 KafkaProducer。
        
        Args:
            config: Kafka 连接配置对象。
            value_serializer: 可选的值序列化器。
            key_serializer: 可选的键序列化器。
            
        Raises:
            ValueError: 如果 bootstrap_servers 未配置。
        """
        if not config.bootstrap_servers:
            raise ValueError("kafka_bootstrap_servers 未配置")

        self._config = config
        self._value_serializer = value_serializer
        
        # 初始化底层 KafkaProducer 实例
        self._producer = KafkaProducer(
            bootstrap_servers=config.bootstrap_servers,
            client_id=config.client_id,
            security_protocol=config.security_protocol,
            sasl_mechanism=config.sasl_mechanism,
            sasl_plain_username=config.sasl_username,
            sasl_plain_password=config.sasl_password,
            acks=config.acks,
            retries=config.retries,
            linger_ms=config.linger_ms,
            batch_size=config.batch_size,
            request_timeout_ms=config.request_timeout_ms,
            value_serializer=value_serializer,
            key_serializer=key_serializer,
        )

    def send(
        self,
        topic: str,
        value: Any,
        key: Optional[Any] = None,
        headers: Optional[Iterable[tuple[str, bytes]]] = None,
        partition: Optional[int] = None,
        timestamp_ms: Optional[int] = None,
    ) -> None:
        """发送原始消息（透传给 KafkaProducer）。
        
        Args:
            topic: 目标 Topic。
            value: 消息体（如果未配置 serializer，需为 bytes）。
            key: 消息键（用于分区路由）。
            headers: 消息头列表。
            partition: 指定分区号。
            timestamp_ms: 消息时间戳。
        """
        self._producer.send(
            topic=topic,
            value=value,
            key=key,
            headers=headers,
            partition=partition,
            timestamp_ms=timestamp_ms,
        )

    def send_json(
        self,
        topic: str,
        payload: Dict[str, Any],
        key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """发送 JSON 格式消息的便捷方法。
        
        自动处理 JSON 序列化、UTF-8 编码以及 Headers 的转换。
        
        Args:
            topic: 目标 Topic。
            payload: 字典格式的消息体。
            key: 字符串格式的消息键（自动编码为 bytes）。
            headers: 字典格式的消息头（自动编码为 bytes）。
        """
        header_list = None
        if headers:
            # 将 headers 字典转换为 Kafka 需要的 [(key, value_bytes)] 列表格式
            header_list = [(k, v.encode("utf-8")) for k, v in headers.items()]
            
        if self._value_serializer is not None:
            # 如果初始化时已提供了序列化器，则直接传入对象，由底层处理
            value = payload
        else:
            # 否则使用默认的 JSON 序列化器手动序列化
            value = _default_json_serializer(payload)
            
        self.send(
            topic=topic,
            value=value,
            key=key.encode("utf-8") if key else None,
            headers=header_list,
        )

    def flush(self) -> None:
        """强制发送缓冲区中的所有消息（阻塞直到完成）。"""
        self._producer.flush()

    def close(self) -> None:
        """关闭 Producer 连接。"""
        self._producer.close()


@lru_cache
def get_kafka_manager(
    value_serializer: Optional[Serializer] = None,
    key_serializer: Optional[Serializer] = None,
) -> KafkaManager:
    """获取 KafkaManager 单例（基于 lru_cache 缓存）。
    
    Args:
        value_serializer: 可选的自定义值序列化器。
        key_serializer: 可选的自定义键序列化器。
        
    Returns:
        KafkaManager 实例。
    """
    config = KafkaProducerConfig.from_settings()
    return KafkaManager(
        config=config,
        value_serializer=value_serializer,
        key_serializer=key_serializer,
    )
