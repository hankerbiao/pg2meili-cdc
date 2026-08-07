"""应用的配置管理模块。"""

from functools import lru_cache
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


SECRET_FILE_FIELDS = (
    "pg_conn_string",
    "open_platform_admin_password_hash",
    "open_platform_session_secret",
    "agent_registration_token",
    "kafka_sasl_password",
    "oa_jwt_secret",
)


class Settings(BaseSettings):
    """从环境变量和 .env 文件加载的应用配置。"""

    # PostgreSQL 连接字符串（必填，通过 .env 或环境变量提供）
    pg_conn_string: str

    # 服务端口
    server_port: str = ":8080"

    # CORS 配置，逗号分隔。留空则不启用 CORS 中间件（仅同源访问）
    cors_allow_origins: str = ""

    # 日志配置
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_rotation: str = "100 MB"
    log_retention: str = "14 days"
    log_backtrace: bool = False
    log_diagnose: bool = False
    log_json: bool = False
    log_file_enabled: bool = True

    # 可选的 Python SDK 下载包；留空时从仓库源码按请求构建
    python_sdk_archive: str = ""

    # 代理节点健康检查配置
    agent_health_path: str = "/health"
    agent_scan_interval_seconds: int = 5
    agent_health_timeout_seconds: int = 5
    agent_online_ttl_seconds: int = 120
    agent_registration_token: str = ""
    # 允许 Agent 使用私网/受限地址的 CIDR 白名单（逗号分隔）。
    # 仅当 Agent 必须落在内网时才配置；留空表示一律禁止受限地址（SSRF 防护）。
    agent_allowed_cidrs: str = ""

    # search_outbox 的 CDC 读取角色（Debezium 快照 SELECT 需绕过 RLS）。
    # 留空则不创建豁免策略：业务角色与复制角色都会被 RLS 限制（仅建议在非标准部署时留空）。
    search_outbox_cdc_role: str = "unidata_cdc"

    # 开放平台管理员与会话配置
    open_platform_admin_username: str = "admin"
    open_platform_admin_password_hash: str = ""
    open_platform_session_secret: str = ""
    open_platform_session_ttl_seconds: int = 28800
    # Cookie 是否标记为 Secure。
    # HTTP（含本地 / 容器 localhost）下浏览器不会发送 Secure Cookie，会导致开放平台
    # 管理员登录会话失效，因此默认关闭。若服务前置 HTTPS / TLS 终止，请改为 true。
    open_platform_cookie_secure: bool = False
    api_key_max_ttl_days: int = 365

    # OA 单点登录（springboard）配置
    oa_jwt_secret: str = ""  # springboard 回调 payload（HS256 JWT）验签密钥；必填，经 .env 注入；缺失时 callback 报 500
    oa_app_name: str = "searchunidatainterface"  # springboard 登录代理应用标识
    oa_login_base_url: str = "http://tl.cooacloud.com/springboard_v3/login_proxy"  # springboard 登录代理地址
    oa_session_ttl_seconds: int = 28800  # OA 普通用户会话有效期（秒）
    oa_cookie_secure: bool = False  # 与 open_platform_cookie_secure 一致；HTTP 下必须 false
    oa_cookie_name: str = "unidata_oa_session"

    # Kafka 配置（必填，通过 .env 或环境变量提供）
    kafka_bootstrap_servers: str
    kafka_client_id: str = "unidata-producer"  # 客户端标识符，用于区分不同的生产者
    kafka_security_protocol: str = (
        "PLAINTEXT"  # 安全协议，可选 PLAINTEXT, SASL_PLAINTEXT, SASL_SSL, SSL
    )
    kafka_sasl_mechanism: Optional[str] = (
        None  # SASL 认证机制，如 PLAIN, SCRAM-SHA-256 等
    )
    kafka_sasl_username: Optional[str] = None  # SASL 认证用户名
    kafka_sasl_password: Optional[str] = None  # SASL 认证密码
    kafka_acks: str = (
        "all"  # 消息确认机制：'0'(不等待), '1'(Leader确认), 'all'(ISR全部确认)
    )
    kafka_retries: int = 3  # 发送失败重试次数
    kafka_linger_ms: int = 10  # 批量发送延迟时间(ms)，增加吞吐量但增加延迟
    kafka_batch_size: int = (
        16384  # 批量发送大小(bytes)，达到此大小或 linger_ms 超时触发发送
    )
    kafka_request_timeout_ms: int = 30000  # 请求超时时间(ms)
    kafka_meili_command_topic: str = "meili.commands"  # Meilisearch 指令专用 Topic
    kafka_api_key_topic: str = "api_keys.events"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def __init__(self, **values):
        for field_name in SECRET_FILE_FIELDS:
            secret_file = os.getenv(f"{field_name.upper()}_FILE", "").strip()
            if not secret_file:
                continue
            try:
                secret = Path(secret_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ValueError(f"无法读取 {field_name.upper()}_FILE") from exc
            values[field_name] = secret
        super().__init__(**values)


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例。"""
    return Settings()
