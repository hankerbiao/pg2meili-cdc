"""测试用例数据库操作的仓储模块。"""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.testcase import TestCase


class TestCaseRepository:
    """测试用例 CRUD 操作的仓储类。"""

    @staticmethod
    async def insert_test_case(
        db: AsyncSession, id: str, payload: bytes
    ) -> None:
        """
        插入或更新测试用例（ORM 方式）。
        """
        existing: Optional[TestCase] = await db.get(TestCase, id)

        payload_text = payload.decode("utf-8")
        try:
            payload_data = json.loads(payload_text)
        except json.JSONDecodeError:
            payload_data = {}

        now = datetime.utcnow()
        if existing:
            existing.payload = payload_data
            existing.updated_at = now
        else:
            obj = TestCase(id=id, payload=payload_data, updated_at=now)
            db.add(obj)

        await db.flush()

    @staticmethod
    async def soft_delete_test_case(db: AsyncSession, id: str) -> None:
        """
        软删除测试用例（ORM 方式，将 payload 中 is_delete 置为 true）。
        """
        obj: Optional[TestCase] = await db.get(TestCase, id)
        if not obj:
            return

        try:
            data = json.loads(obj.payload) if obj.payload else {}
        except json.JSONDecodeError:
            data = {}

        data["is_delete"] = True
        obj.payload = json.dumps(data, ensure_ascii=False)
        obj.updated_at = datetime.utcnow()

        await db.flush()

    @staticmethod
    async def get_test_case(db: AsyncSession, id: str) -> Optional[TestCase]:
        """根据 ID 获取测试用例（ORM 方式）。"""
        return await db.get(TestCase, id)


testcase_repository = TestCaseRepository()
