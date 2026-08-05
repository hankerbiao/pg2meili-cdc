"""集合聚合与设置持久化的服务层测试。

验证：
1. list_collections 按 app 聚合 uni_documents，返回文档数、首末时间与样本字段；
2. update_settings 将「期望态」落库（collection_settings），且不依赖 Kafka 可用性。
"""

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.open_platform import OpenPlatformApp
from app.schemas.document import CollectionSettingsUpdate
from app.services.collection_service import collection_service


@pytest.mark.asyncio
async def test_list_collections_aggregates_docs(db_session: AsyncSession) -> None:
    app = OpenPlatformApp(
        id="test-app-coll",
        app_name="test_app_coll",
        display_name="t",
        owner_itcode="tester",
        status="active",
    )
    db_session.add(app)
    await db_session.flush()
    # 最新样本文档（updated_at 更大）决定 discovered fields
    db_session.add(Document(
        row_id=uuid.uuid4(), id="d1", app_id=app.id, collection="bugs",
        app_name=app.app_name, payload={"title": "x", "status": 1},
        updated_at=datetime(2020, 1, 1), is_delete=False,
    ))
    db_session.add(Document(
        row_id=uuid.uuid4(), id="d2", app_id=app.id, collection="bugs",
        app_name=app.app_name, payload={"title": "y", "priority": 2},
        updated_at=datetime(2020, 1, 2), is_delete=False,
    ))
    await db_session.flush()

    summaries = await collection_service.list_collections(db_session, app.id)
    assert len(summaries) == 1
    assert summaries[0].collection == "bugs"
    assert summaries[0].doc_count == 2
    # 字段取自最新一条样本文档（DISTINCT ON updated_at DESC）
    assert set(summaries[0].fields) == {"title", "priority"}


@pytest.mark.asyncio
async def test_update_and_read_settings(db_session: AsyncSession) -> None:
    app = OpenPlatformApp(
        id="test-app-coll-2",
        app_name="test_app_coll_2",
        display_name="t",
        owner_itcode="tester",
        status="active",
    )
    db_session.add(app)
    await db_session.flush()
    db_session.add(Document(
        row_id=uuid.uuid4(), id="d1", app_id=app.id, collection="bugs",
        app_name=app.app_name, payload={"title": "x"}, is_delete=False,
    ))
    await db_session.flush()

    with patch("app.services.collection_service.index_service.update_index_settings") as mock_send:
        detail = await collection_service.update_settings(
            db_session,
            app.id,
            app.app_name,
            "bugs",
            CollectionSettingsUpdate(filterableAttributes=["title"], sortableAttributes=["title"]),
        )
        mock_send.assert_called_once()

    assert detail.filterable_attributes == ["title"]
    assert detail.sortable_attributes == ["title"]

    # 再次读取应反映已保存的期望态
    reread = await collection_service.get_collection(db_session, app.id, "bugs")
    assert reread.filterable_attributes == ["title"]
    assert reread.sortable_attributes == ["title"]
