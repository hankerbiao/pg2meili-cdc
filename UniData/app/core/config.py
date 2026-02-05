"""应用的配置管理模块。"""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量和 .env 文件加载的应用配置。"""

    # PostgreSQL 连接字符串
    pg_conn_string: str = "postgres://postgres:kk123123@10.17.154.252:5432/postgres"

    # 服务端口
    server_port: str = ":8080"

    # CORS 配置，逗号分隔。使用 "*" 表示允许所有来源
    cors_allow_origins: str = "*"

    # 日志配置
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_rotation: str = "100 MB"
    log_retention: str = "14 days"
    log_backtrace: bool = False
    log_diagnose: bool = False
    log_json: bool = False

    # 代理节点健康检查配置
    agent_health_path: str = "/health"
    agent_scan_interval_seconds: int = 5
    agent_health_timeout_seconds: int = 5
    agent_online_ttl_seconds: int = 120

    # 默认 Meilisearch 端点配置（可选）
    meili_default_url: Optional[str] = ""
    meili_default_api_key: Optional[str] = ""

    # JWT 签名秘钥（HS256）
    jwt_secret: str = "dYAj4kPbhIdCM35XhcDW9HJX53xT3iux"

    # Kafka 配置
    kafka_bootstrap_servers: str = "http://10.17.154.252:9092"  # Kafka 集群地址，格式如 "host1:9092,host2:9092"
    kafka_client_id: str = "unidata-producer"  # 客户端标识符，用于区分不同的生产者
    kafka_security_protocol: str = "PLAINTEXT"  # 安全协议，可选 PLAINTEXT, SASL_PLAINTEXT, SASL_SSL, SSL
    kafka_sasl_mechanism: Optional[str] = None  # SASL 认证机制，如 PLAIN, SCRAM-SHA-256 等
    kafka_sasl_username: Optional[str] = None  # SASL 认证用户名
    kafka_sasl_password: Optional[str] = None  # SASL 认证密码
    kafka_acks: str = "all"  # 消息确认机制：'0'(不等待), '1'(Leader确认), 'all'(ISR全部确认)
    kafka_retries: int = 3  # 发送失败重试次数
    kafka_linger_ms: int = 10  # 批量发送延迟时间(ms)，增加吞吐量但增加延迟
    kafka_batch_size: int = 16384  # 批量发送大小(bytes)，达到此大小或 linger_ms 超时触发发送
    kafka_request_timeout_ms: int = 30000  # 请求超时时间(ms)
    kafka_meili_command_topic: str = "meili.commands"  # Meilisearch 指令专用 Topic

    gquan_base_url: Optional[str] = "http://10.32.129.1/springboard_v3"
    gquan_app_name: Optional[str] = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例。"""
    return Settings()
