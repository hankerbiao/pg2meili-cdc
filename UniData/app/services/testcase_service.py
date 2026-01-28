"""测试用例业务逻辑的服务层模块。"""
import json
import logging
from typing import Any, Dict
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.testcase_repository import testcase_repository

logger = logging.getLogger(__name__)


class TestCaseService:
    """测试用例的业务逻辑类。"""

    @staticmethod
    async def create_test_case(db: AsyncSession, body_bytes: bytes) -> str:
        """
        创建或更新测试用例。

        1. 解析请求体以提取 id 字段
        2. 插入/更新到 test_cases 表
        3. 返回 id
        """
        # 解析请求体以提取 id 字段
        try:
            payload = json.loads(body_bytes)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的 JSON 格式",
            )

        # 检查必需的 id 字段
        if "id" not in payload or not payload["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="缺少 'id' 字段",
            )

        id_value = payload["id"]
        payload["id"] = id_value

        # 重新编码 payload 为字节
        try:
            body_bytes = json.dumps(payload).encode("utf-8")
        except (TypeError, ValueError) as e:
            logger.error(f"编码 payload 失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="内部服务器错误",
            )

        # 插入数据库
        try:
            await testcase_repository.insert_test_case(db, id_value, body_bytes)
        except Exception as e:
            logger.error(f"插入测试用例失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库错误",
            )

        return id_value

    @staticmethod
    async def delete_test_case(db: AsyncSession, id: str) -> str:
        """
        软删除测试用例。

        在 payload JSONB 中设置 is_delete 为 true。
        """
        try:
            await testcase_repository.soft_delete_test_case(db, id)
        except Exception as e:
            logger.error(f"软删除测试用例失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库错误",
            )

        return id


testcase_service = TestCaseService()
