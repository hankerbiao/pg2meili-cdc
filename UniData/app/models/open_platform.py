"""开放平台应用、API Key、审计与事件模型。"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OpenPlatformApp(Base):
    __tablename__ = "open_platform_apps"

    id = Column(String, primary_key=True, nullable=False)
    app_name = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False)
    owner_itcode = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="active", index=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("app_id", "name", name="uq_api_keys_app_name"),)

    id = Column(String, primary_key=True, nullable=False)
    app_id = Column(String, ForeignKey("open_platform_apps.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    secret_hash = Column(String(64), nullable=False)
    last_four = Column(String(4), nullable=False)
    scopes = Column(JSONB, nullable=False)
    status = Column(String, nullable=False, default="active", index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class OpenPlatformAuditLog(Base):
    __tablename__ = "open_platform_audit_logs"

    id = Column(String, primary_key=True, nullable=False)
    actor = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=True, index=True)
    app_id = Column(String, nullable=True, index=True)
    source_ip = Column(String, nullable=True)
    details = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class OpenPlatformOutbox(Base):
    __tablename__ = "open_platform_outbox"

    id = Column(String, primary_key=True, nullable=False)
    aggregate_key = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
