import asyncio
import os
import sys
from typing import NoReturn

# 确保可以从项目根目录导入 app 包
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.core.database import engine
from app.models.testcase import Base


async def _create_all() -> None:
    """
    初始化数据库中所有由 SQLAlchemy Base 管理的表。

    包含：
    - test_cases（测试用例表）
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def main() -> NoReturn:
    """
    便捷脚本入口：

    在项目根目录下运行：
      python3 scripts/create_all.py
    """
    asyncio.run(_create_all())
    print("✅ 数据库表已初始化（如果不存在则创建）。")


if __name__ == "__main__":
    main()
