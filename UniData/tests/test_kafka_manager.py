"""KafkaManager 单元测试（无需真实 Kafka / Postgres）。

通过 mock 底层 KafkaProducer 验证：配置工厂、序列化、send/send_json 透传、
flush/close 调用，以及 get_kafka_manager 的 lru_cache 单例行为。
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from app.core.kafka_manager import (
    KafkaManager,
    KafkaProducerConfig,
    _default_json_serializer,
    get_kafka_manager,
)


def _cfg() -> KafkaProducerConfig:
    return KafkaProducerConfig(
        bootstrap_servers="127.0.0.1:9092",
        client_id="unidata-test",
        security_protocol="PLAINTEXT",
        sasl_mechanism=None,
        sasl_username=None,
        sasl_password=None,
        acks="all",
        retries=3,
        linger_ms=5,
        batch_size=16384,
        request_timeout_ms=30000,
    )


def test_default_json_serializer_is_unicode_compact():
    out = _default_json_serializer({"name": "键盘", "n": 1})
    # ensure_ascii=False 保留中文，且不带分隔空格
    assert out == "{\"name\":\"键盘\",\"n\":1}".encode("utf-8")
    assert b", " not in out  # 去空格


def test_config_from_settings_reads_values(monkeypatch):
    class _S:
        kafka_bootstrap_servers = "k:9092"
        kafka_client_id = "cid"
        kafka_security_protocol = "SASL_SSL"
        kafka_sasl_mechanism = "PLAIN"
        kafka_sasl_username = "u"
        kafka_sasl_password = "p"
        kafka_acks = "1"
        kafka_retries = 5
        kafka_linger_ms = 10
        kafka_batch_size = 100
        kafka_request_timeout_ms = 1000

    monkeypatch.setattr("app.core.kafka_manager.get_settings", lambda: _S())
    cfg = KafkaProducerConfig.from_settings()
    assert cfg.bootstrap_servers == "k:9092"
    assert cfg.security_protocol == "SASL_SSL"


def test_init_raises_without_bootstrap_servers():
    with pytest.raises(ValueError):
        KafkaManager(replace(_cfg(), bootstrap_servers=""))


def test_init_passes_config_to_producer():
    with patch("app.core.kafka_manager.KafkaProducer") as Prod:
        KafkaManager(_cfg())
        _, kwargs = Prod.call_args
        assert kwargs["bootstrap_servers"] == "127.0.0.1:9092"
        assert kwargs["acks"] == "all"
        assert kwargs["value_serializer"] is None


def test_send_transparently_forwards():
    with patch("app.core.kafka_manager.KafkaProducer") as Prod:
        producer = MagicMock()
        Prod.return_value = producer
        mgr = KafkaManager(_cfg())
        mgr.send("topic", b"value", key=b"k", headers=[("h", b"v")], partition=0)
        producer.send.assert_called_once_with(
            topic="topic", value=b"value", key=b"k", headers=[("h", b"v")], partition=0, timestamp_ms=None
        )


def test_send_json_serializes_and_encodes_headers():
    with patch("app.core.kafka_manager.KafkaProducer") as Prod:
        producer = MagicMock()
        Prod.return_value = producer
        mgr = KafkaManager(_cfg())  # 无 value_serializer -> 走默认 JSON
        mgr.send_json("t", {"a": 1}, key="k", headers={"X": "y"})
        producer.send.assert_called_once()
        _, kwargs = producer.send.call_args
        assert kwargs["value"] == b'{"a":1}'
        assert kwargs["key"] == b"k"
        assert kwargs["headers"] == [("X", b"y")]


def test_send_json_with_custom_serializer_passes_object():
    with patch("app.core.kafka_manager.KafkaProducer") as Prod:
        producer = MagicMock()
        Prod.return_value = producer
        serializer = MagicMock(return_value=b"RAW")
        mgr = KafkaManager(_cfg(), value_serializer=serializer)
        mgr.send_json("t", {"a": 1}, key="k")
        # 自定义序列化器存在时，直接把对象交给底层，由底层序列化
        _, kwargs = producer.send.call_args
        assert kwargs["value"] == {"a": 1}


def test_flush_and_close_delegate():
    with patch("app.core.kafka_manager.KafkaProducer") as Prod:
        producer = MagicMock()
        Prod.return_value = producer
        mgr = KafkaManager(_cfg())
        mgr.flush()
        mgr.close()
        producer.flush.assert_called_once()
        producer.close.assert_called_once()


def test_get_kafka_manager_is_cached_singleton():
    with patch("app.core.kafka_manager.KafkaProducer") as Prod:
        Prod.return_value = MagicMock()
        # 先清缓存，确保可重复
        get_kafka_manager.cache_clear()
        a = get_kafka_manager()
        b = get_kafka_manager()
        assert a is b
        get_kafka_manager.cache_clear()
