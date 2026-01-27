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

    # 默认 Meilisearch 端点配置（可选）
    meili_default_url: Optional[str] = ""
    meili_default_api_key: Optional[str] = ""

    # JWT 签名秘钥（HS256）
    jwt_secret: str = "change-me-in-prod"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例。"""
    return Settings()
