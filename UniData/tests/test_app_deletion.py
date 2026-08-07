"""P0.2 应用删除异步状态机 + 删除期间拒写（409 APP_DELETING）测试。

需要环境变量 TEST_PG_CONN_STRING 指向独立的 test 库，否则用例自动 skip
（与仓库内其它集成测试一致）。
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OpenPlatformApp
from app.models.cleanup_task import (
    AppCleanupTask,
    CLEANUP_STATE_DELETED,
    CLEANUP_STATE_DELETING,
    CLEANUP_STATE_FAILED,
    CLEANUP_STATE_INDEXES_PENDING,
)
from app.core.database import get_db
from app.main import app
from app.services import cleanup_service
from app.services.open_platform_service import open_platform_service, utc_now
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def key_client(db_session: AsyncSession):
    """仅覆盖 get_db，使用真实 API Key 鉴权（不覆盖 get_current_app）。"""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def issue_key(db_session: AsyncSession):
    """在 test-app-id 下签发真实密钥，支持注入过期/吊销等状态（仅 flush 不提交）。"""
    async def _issue(scopes=("data:read", "data:write"), days: int = 90, mutate=None):
        key, plaintext = await open_platform_service.create_key(
            db_session,
            app_id="test-app-id",
            name="auth-test-key",
            scopes=list(scopes),
            expires_at=utc_now() + timedelta(days=days),
            actor="test",
            source_ip=None,
        )
        if mutate is not None:
            mutate(key)
            await db_session.flush()
        return plaintext
    return _issue


# ===========================================================================
# 删除期间拒写保护：数据面写入返回 409 APP_DELETING
# ===========================================================================
class TestWriteRejectedDuringDeletion:
    async def test_write_rejected_during_deleting(self, key_client, issue_key, db_session):
        plaintext = await issue_key(scopes=("data:read", "data:write"), days=90)
        app = await db_session.get(OpenPlatformApp, "test-app-id")
        app.status = "deleting"
        await db_session.flush()

        resp = await key_client.post(
            "/api/v1/data/products",
            json={"id": "x1", "name": "a"},
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "APP_DELETING"

    async def test_write_rejected_after_deleted(self, key_client, issue_key, db_session):
        plaintext = await issue_key(scopes=("data:read", "data:write"), days=90)
        app = await db_session.get(OpenPlatformApp, "test-app-id")
        app.status = "deleted"
        await db_session.flush()

        resp = await key_client.post(
            "/api/v1/data/products",
            json={"id": "x1", "name": "a"},
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "APP_DELETING"

    async def test_write_allowed_when_active(self, key_client, issue_key):
        plaintext = await issue_key(scopes=("data:read", "data:write"), days=90)
        resp = await key_client.post(
            "/api/v1/data/products",
            json={"id": "ok1", "name": "b"},
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert resp.status_code in (200, 201)


# ===========================================================================
# 清理状态机：可恢复、幂等、终态正确
# ===========================================================================
def _patch_infra(monkeypatch, *, collections, regions=("test-region",), delete_side_effect=None):
    """把清理所需的外部依赖打桩，避免依赖真实 Kafka / Meili / 租户 schema。"""

    async def fake_iter(*args, **kwargs):
        for c in collections:
            yield c

    async def fake_delete_index_async(*args, **kwargs):
        if delete_side_effect is not None:
            delete_side_effect()
        return "idx"

    async def fake_drop_tenant(*args, **kwargs):
        return "tenant"

    monkeypatch.setattr(cleanup_service.document_repository, "iter_collections_by_app", fake_iter)

    async def fake_collections_to_cleanup(*args, **kwargs):
        return sorted(set(collections))

    monkeypatch.setattr(cleanup_service, "_collections_to_cleanup", fake_collections_to_cleanup)
    monkeypatch.setattr(cleanup_service.index_service, "delete_index_async", fake_delete_index_async)
    monkeypatch.setattr(cleanup_service, "drop_tenant", fake_drop_tenant)

    async def fake_snapshot_regions(*args, **kwargs):
        return list(regions)

    monkeypatch.setattr(cleanup_service, "_snapshot_target_regions", fake_snapshot_regions)


async def _confirm_all(task):
    for record in task.collection_cleanup:
        for region in task.target_regions or []:
            cleanup_service.record_cleanup_confirmation(task, record["collection"], region)


async def _make_app(db_session: AsyncSession, app_id: str) -> OpenPlatformApp:
    app = OpenPlatformApp(
        id=app_id,
        app_name=app_id,
        display_name=app_id,
        owner_itcode="pytest",
        status="active",
        version=1,
    )
    db_session.add(app)
    await db_session.flush()
    return app


class TestCleanupStateMachine:
    async def test_run_cleanup_task_completes_deleted(self, db_session, monkeypatch):
        app = await _make_app(db_session, "sm-app-1")
        _patch_infra(monkeypatch, collections=["c1", "c2"])
        task = await cleanup_service.create_task(db_session, app_id=app.id, app_name=app.app_name)

        await cleanup_service.run_cleanup_task(db_session, task)

        assert task.state == CLEANUP_STATE_INDEXES_PENDING
        assert task.attempts == 1
        assert all(r["status"] == "command_sent" for r in task.collection_cleanup)
        assert {r["collection"] for r in task.collection_cleanup} == {"c1", "c2"}
        await _confirm_all(task)
        await cleanup_service.run_cleanup_task(db_session, task)
        assert task.state == CLEANUP_STATE_DELETED

    async def test_run_cleanup_task_empty_collections_still_deleted(self, db_session, monkeypatch):
        app = await _make_app(db_session, "sm-app-empty")
        _patch_infra(monkeypatch, collections=[])
        task = await cleanup_service.create_task(db_session, app_id=app.id, app_name=app.app_name)

        await cleanup_service.run_cleanup_task(db_session, task)

        assert task.state == CLEANUP_STATE_DELETED
        assert task.collection_cleanup == []

    async def test_run_cleanup_task_resumes_after_failure(self, db_session, monkeypatch):
        app = await _make_app(db_session, "sm-app-resume")
        _patch_infra(monkeypatch, collections=["c1", "c2"])
        calls = {"n": 0}

        def _boom():
            calls["n"] += 1
            raise RuntimeError("meili unavailable")

        # 第一次运行：c1 删除失败 -> cleanup_failed
        task = await cleanup_service.create_task(db_session, app_id=app.id, app_name=app.app_name)
        cleanup_service.index_service.delete_index_async = _async_boom(_boom)
        with pytest.raises(RuntimeError):
            await cleanup_service.run_cleanup_task(db_session, task)
        assert task.state == CLEANUP_STATE_FAILED
        await db_session.commit()
        await db_session.refresh(task)

        # 第二次运行：恢复并成功完成，c1 被重试、c2 也被处理
        async def _ok(*args, **kwargs):
            return "idx"

        monkeypatch.setattr(cleanup_service.index_service, "delete_index_async", _ok)
        await cleanup_service.run_cleanup_task(db_session, task)
        await _confirm_all(task)
        await cleanup_service.run_cleanup_task(db_session, task)
        assert task.state == CLEANUP_STATE_DELETED
        assert all(r["status"] == "confirmed" for r in task.collection_cleanup)
        # c1 至少被尝试两次（首次失败 + 重试），c2 一次
        c1 = next(r for r in task.collection_cleanup if r["collection"] == "c1")
        assert c1["attempts"] >= 2

    async def test_delete_app_marks_deleting_and_finalizes(self, db_session, monkeypatch):
        """delete_app 应标记 deleting、创建 cleanup task，并在清理完成后置为 deleted。"""
        app = await _make_app(db_session, "del-app-1")
        _patch_infra(monkeypatch, collections=["c1"])

        # 用同会话内联执行清理（避免依赖全局 engine / Kafka）。
        async def fake_run_by_id(task_id):
            t = await db_session.get(AppCleanupTask, task_id)
            await cleanup_service.run_cleanup_task(db_session, t)
            await _confirm_all(t)
            await cleanup_service.run_cleanup_task(db_session, t)

        monkeypatch.setattr(cleanup_service, "run_cleanup_task_by_id", fake_run_by_id)

        result = await open_platform_service.delete_app(
            db_session, app_id=app.id, actor="test:tester", source_ip=None
        )
        # 清理内联完成后应直接到 deleted
        assert result.status == "deleted"
        task = await cleanup_service.get_task(db_session, app.id)
        assert task is not None
        assert task.state == CLEANUP_STATE_DELETED


# ===========================================================================
# 状态机纯逻辑单测（无需真实 Postgres）：用假 session 验证状态转移与可恢复性
# ===========================================================================
class _FakeSession:
    """仅实现 run_cleanup_task 用到的 db 接口，避免依赖真实数据库。"""
    async def flush(self):
        return None

    async def refresh(self, obj):
        return None

    async def commit(self):
        return None

    async def get(self, cls, pk):
        return None


class TestCleanupStateMachineUnit:
    async def test_run_cleanup_task_completes_without_db(self, monkeypatch):
        _patch_infra(monkeypatch, collections=["c1", "c2"])
        task = AppCleanupTask(id="t1", app_id="a1", app_name="a1", state=CLEANUP_STATE_DELETING)
        await cleanup_service.run_cleanup_task(_FakeSession(), task)
        assert task.state == CLEANUP_STATE_INDEXES_PENDING
        assert task.attempts == 1
        assert all(r["status"] == "command_sent" for r in task.collection_cleanup)
        assert {r["collection"] for r in task.collection_cleanup} == {"c1", "c2"}
        await _confirm_all(task)
        await cleanup_service.run_cleanup_task(_FakeSession(), task)
        assert task.state == CLEANUP_STATE_DELETED

    async def test_resume_after_failure_without_db(self, monkeypatch):
        _patch_infra(monkeypatch, collections=["c1", "c2"])
        task = AppCleanupTask(id="t2", app_id="a2", app_name="a2", state=CLEANUP_STATE_DELETING)
        boom = {"n": 0}

        async def _boom(*args, **kwargs):
            boom["n"] += 1
            raise RuntimeError("meili down")

        monkeypatch.setattr(cleanup_service.index_service, "delete_index_async", _boom)
        with pytest.raises(RuntimeError):
            await cleanup_service.run_cleanup_task(_FakeSession(), task)
        assert task.state == CLEANUP_STATE_FAILED

        async def _ok(*args, **kwargs):
            return "idx"

        monkeypatch.setattr(cleanup_service.index_service, "delete_index_async", _ok)
        await cleanup_service.run_cleanup_task(_FakeSession(), task)
        await _confirm_all(task)
        await cleanup_service.run_cleanup_task(_FakeSession(), task)
        assert task.state == CLEANUP_STATE_DELETED
        assert all(r["status"] == "confirmed" for r in task.collection_cleanup)
        c1 = next(r for r in task.collection_cleanup if r["collection"] == "c1")
        assert c1["attempts"] >= 2  # c1 首次失败 + 重试

    async def test_empty_collections_still_deleted_without_db(self, monkeypatch):
        _patch_infra(monkeypatch, collections=[])
        task = AppCleanupTask(id="t3", app_id="a3", app_name="a3", state=CLEANUP_STATE_DELETING)
        await cleanup_service.run_cleanup_task(_FakeSession(), task)
        assert task.state == CLEANUP_STATE_DELETED
        assert task.collection_cleanup == []

    async def test_confirmation_requires_all_regions_and_is_idempotent(self, monkeypatch):
        _patch_infra(monkeypatch, collections=["c1"], regions=("cn-bj", "cn-sh"))
        task = AppCleanupTask(id="t4", app_id="a4", app_name="a4", state=CLEANUP_STATE_DELETING)
        await cleanup_service.run_cleanup_task(_FakeSession(), task)
        assert task.state == CLEANUP_STATE_INDEXES_PENDING
        assert cleanup_service.record_cleanup_confirmation(task, "c1", "cn-bj") is True
        assert cleanup_service.record_cleanup_confirmation(task, "c1", "cn-bj") is False
        await cleanup_service.run_cleanup_task(_FakeSession(), task)
        assert task.state == CLEANUP_STATE_INDEXES_PENDING
        assert cleanup_service.record_cleanup_confirmation(task, "c1", "cn-sh") is True
        await cleanup_service.run_cleanup_task(_FakeSession(), task)
        assert task.state == CLEANUP_STATE_DELETED

    async def test_cleanup_without_online_region_fails_safely(self, monkeypatch):
        _patch_infra(monkeypatch, collections=["c1"], regions=())
        task = AppCleanupTask(id="t5", app_id="a5", app_name="a5", state=CLEANUP_STATE_DELETING)
        with pytest.raises(RuntimeError, match="没有在线"):
            await cleanup_service.run_cleanup_task(_FakeSession(), task)
        assert task.state == CLEANUP_STATE_FAILED


def _async_boom(side_effect):
    async def _f(*args, **kwargs):
        side_effect()
        return "idx"

    return _f
