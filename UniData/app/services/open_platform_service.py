"""开放平台应用、API Key、审计、快照与 outbox 服务。"""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.core.kafka_manager import get_kafka_manager
from app.models.open_platform import ApiKey, OpenPlatformApp, OpenPlatformAuditLog, OpenPlatformOutbox


ALLOWED_SCOPES = {"search:read", "data:read", "data:write"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_api_key() -> tuple[str, str, str]:
    """返回 Key ID、一次性明文与可持久化的摘要。"""
    key_id = f"ak_{secrets.token_hex(8)}"
    secret = secrets.token_urlsafe(32)
    plaintext = f"ud_live_{key_id}.{secret}"
    return key_id, plaintext, hashlib.sha256(secret.encode()).hexdigest()


def key_event(key: ApiKey, app: OpenPlatformApp, event_type: str = "key.upsert") -> dict[str, Any]:
    return {
        "version": 1,
        "event": event_type,
        "key_id": key.id,
        "app_id": app.id,
        "app_name": app.app_name,
        "secret_hash": key.secret_hash,
        "scopes": list(key.scopes or []),
        "status": key.status,
        "expires_at": key.expires_at.isoformat(),
        "resource_version": key.version,
        "ts": int(utc_now().timestamp()),
    }


def app_event(app: OpenPlatformApp) -> dict[str, Any]:
    return {
        "version": 1,
        "event": "app.upsert",
        "app_id": app.id,
        "app_name": app.app_name,
        "status": app.status,
        "resource_version": app.version,
        "ts": int(utc_now().timestamp()),
    }


class OpenPlatformService:
    @staticmethod
    def _add_outbox(db: AsyncSession, aggregate_key: str, event_type: str, payload: dict[str, Any]) -> None:
        db.add(OpenPlatformOutbox(
            id=uuid.uuid4().hex,
            aggregate_key=aggregate_key,
            event_type=event_type,
            payload=payload,
        ))

    @staticmethod
    def add_audit(
        db: AsyncSession,
        *,
        actor: str,
        action: str,
        target_type: str,
        target_id: str | None = None,
        app_id: str | None = None,
        source_ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        db.add(OpenPlatformAuditLog(
            id=uuid.uuid4().hex,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            app_id=app_id,
            source_ip=source_ip,
            details=details,
        ))

    @staticmethod
    async def list_apps(db: AsyncSession, app_status: str | None = None) -> list[OpenPlatformApp]:
        query = select(OpenPlatformApp).order_by(OpenPlatformApp.created_at.desc())
        if app_status:
            query = query.where(OpenPlatformApp.status == app_status)
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def get_app(db: AsyncSession, app_id: str) -> OpenPlatformApp:
        app = await db.get(OpenPlatformApp, app_id)
        if app is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")
        return app

    @classmethod
    async def create_app(
        cls,
        db: AsyncSession,
        *,
        app_name: str,
        display_name: str,
        owner_itcode: str,
        description: str | None,
        actor: str,
        source_ip: str | None,
    ) -> OpenPlatformApp:
        existing = await db.scalar(select(OpenPlatformApp.id).where(OpenPlatformApp.app_name == app_name))
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="app_name 已存在")
        app = OpenPlatformApp(
            id=uuid.uuid4().hex,
            app_name=app_name,
            display_name=display_name,
            owner_itcode=owner_itcode,
            description=description,
            status="active",
            version=1,
        )
        db.add(app)
        await db.flush()
        cls._add_outbox(db, app.id, "app.upsert", app_event(app))
        cls.add_audit(db, actor=actor, action="app.create", target_type="app", target_id=app.id, app_id=app.id, source_ip=source_ip)
        return app

    @classmethod
    async def update_app(cls, db: AsyncSession, app_id: str, changes: dict[str, Any], actor: str, source_ip: str | None) -> OpenPlatformApp:
        app = await cls.get_app(db, app_id)
        for field in ("display_name", "owner_itcode", "description", "status"):
            if field in changes and changes[field] is not None:
                setattr(app, field, changes[field])
        app.version += 1
        app.updated_at = utc_now()
        await db.flush()
        cls._add_outbox(db, app.id, "app.upsert", app_event(app))
        cls.add_audit(db, actor=actor, action="app.update", target_type="app", target_id=app.id, app_id=app.id, source_ip=source_ip, details=changes)
        return app

    @staticmethod
    async def list_keys(db: AsyncSession, app_id: str) -> list[ApiKey]:
        return list((await db.execute(select(ApiKey).where(ApiKey.app_id == app_id).order_by(ApiKey.created_at.desc()))).scalars().all())

    @staticmethod
    def _validate_scopes(scopes: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(scopes))
        if not normalized or any(scope not in ALLOWED_SCOPES for scope in normalized):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="API Key 权限无效")
        return normalized

    @classmethod
    async def create_key(
        cls,
        db: AsyncSession,
        *,
        app_id: str,
        name: str,
        scopes: list[str],
        expires_at: datetime,
        actor: str,
        source_ip: str | None,
    ) -> tuple[ApiKey, str]:
        app = await cls.get_app(db, app_id)
        if app.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="禁用应用不能创建 API Key")
        scopes = cls._validate_scopes(scopes)
        now = utc_now()
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        max_expiry = now + timedelta(days=get_settings().api_key_max_ttl_days)
        if expires_at <= now or expires_at > max_expiry:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="有效期必须在未来 1 至 365 天内")
        existing = await db.scalar(select(ApiKey.id).where(ApiKey.app_id == app_id, ApiKey.name == name))
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该应用下的 Key 名称已存在")

        key_id, plaintext, secret_hash = generate_api_key()
        secret = plaintext.rsplit(".", 1)[1]
        key = ApiKey(
            id=key_id,
            app_id=app.id,
            name=name,
            secret_hash=secret_hash,
            last_four=secret[-4:],
            scopes=scopes,
            status="active",
            expires_at=expires_at,
            version=1,
        )
        db.add(key)
        await db.flush()
        cls._add_outbox(db, key.id, "key.upsert", key_event(key, app))
        cls.add_audit(db, actor=actor, action="key.create", target_type="api_key", target_id=key.id, app_id=app.id, source_ip=source_ip, details={"name": name, "scopes": scopes})
        return key, plaintext

    @classmethod
    async def revoke_key(cls, db: AsyncSession, key_id: str, actor: str, source_ip: str | None) -> ApiKey:
        key = await db.get(ApiKey, key_id)
        if key is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
        if key.status == "revoked":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="API Key 已撤销")
        app = await cls.get_app(db, key.app_id)
        key.status = "revoked"
        key.revoked_at = utc_now()
        key.updated_at = utc_now()
        key.version += 1
        await db.flush()
        cls._add_outbox(db, key.id, "key.revoked", key_event(key, app, "key.revoked"))
        cls.add_audit(db, actor=actor, action="key.revoke", target_type="api_key", target_id=key.id, app_id=app.id, source_ip=source_ip)
        return key

    @classmethod
    async def rotate_key(cls, db: AsyncSession, key_id: str, actor: str, source_ip: str | None) -> tuple[ApiKey, str]:
        old_key = await db.get(ApiKey, key_id)
        if old_key is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
        if old_key.status == "revoked":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已撤销的 API Key 不能轮换")
        app = await cls.get_app(db, old_key.app_id)
        old_name = old_key.name
        old_key.name = f"{old_name}-revoked-{old_key.id[-6:]}"
        await cls.revoke_key(db, key_id, actor, source_ip)
        new_key, plaintext = await cls.create_key(
            db,
            app_id=app.id,
            name=old_name,
            scopes=list(old_key.scopes),
            expires_at=old_key.expires_at,
            actor=actor,
            source_ip=source_ip,
        )
        cls.add_audit(db, actor=actor, action="key.rotate", target_type="api_key", target_id=new_key.id, app_id=app.id, source_ip=source_ip, details={"replaced_key_id": old_key.id})
        return new_key, plaintext

    @staticmethod
    async def list_audit_logs(
        db: AsyncSession,
        app_id: str | None,
        action: str | None,
        from_time: datetime | None,
        to_time: datetime | None,
        offset: int,
        limit: int,
    ) -> list[OpenPlatformAuditLog]:
        query = select(OpenPlatformAuditLog).order_by(OpenPlatformAuditLog.created_at.desc()).offset(offset).limit(limit)
        if app_id:
            query = query.where(OpenPlatformAuditLog.app_id == app_id)
        if action:
            query = query.where(OpenPlatformAuditLog.action == action)
        if from_time:
            query = query.where(OpenPlatformAuditLog.created_at >= from_time)
        if to_time:
            query = query.where(OpenPlatformAuditLog.created_at <= to_time)
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def snapshot(db: AsyncSession) -> dict[str, Any]:
        apps = list((await db.execute(select(OpenPlatformApp))).scalars().all())
        keys = list((await db.execute(select(ApiKey).where(ApiKey.status == "active"))).scalars().all())
        return {
            "apps": [app_event(app) for app in apps],
            "keys": [key_event(key, next(app for app in apps if app.id == key.app_id)) for key in keys],
        }


async def publish_outbox_once() -> int:
    async with get_db_context() as db:
        events = list((await db.execute(
            select(OpenPlatformOutbox)
            .where(OpenPlatformOutbox.published_at.is_(None))
            .order_by(OpenPlatformOutbox.created_at)
            .limit(50)
        )).scalars().all())
        if not events:
            return 0
        settings = get_settings()
        try:
            kafka = await asyncio.to_thread(get_kafka_manager)
            for event in events:
                await asyncio.to_thread(kafka.send_json, settings.kafka_api_key_topic, event.payload, event.aggregate_key)
            await asyncio.to_thread(kafka.flush)
            now = utc_now()
            for event in events:
                event.published_at = now
                event.last_error = None
            return len(events)
        except Exception as exc:
            for event in events:
                event.attempts += 1
                event.last_error = str(exc)[:1000]
            logger.error("发布开放平台 outbox 失败: {}", exc)
            return 0


async def publish_outbox_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await publish_outbox_once()
        except Exception as exc:
            logger.error("开放平台 outbox 循环失败: {}", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=1.0)
        except TimeoutError:
            pass


open_platform_service = OpenPlatformService()
