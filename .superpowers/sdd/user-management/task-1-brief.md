# Task 1: 数据库迁移 — 创建 open_platform_users 表

## Files
- Create: `UniData/migrations/migrate_add_open_platform_users.py`

## Step 1: 创建迁移脚本

创建文件 `UniData/migrations/migrate_add_open_platform_users.py`，内容如下：

```python
"""添加 open_platform_users 表。"""
from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# 使用与 app 相同的数据库连接
DATABASE_URL = "postgresql+asyncpg://postgres:change-me@postgres:5432/postgres"


async def upgrade() -> None:
    """创建 open_platform_users 表。"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS open_platform_users (
                id VARCHAR NOT NULL PRIMARY KEY,
                username VARCHAR NOT NULL UNIQUE,
                display_name VARCHAR NOT NULL,
                password_hash VARCHAR NOT NULL,
                status VARCHAR NOT NULL DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_open_platform_users_username ON open_platform_users (username)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_open_platform_users_status ON open_platform_users (status)"))
    await engine.dispose()
    print("Migration complete: open_platform_users table created")


async def downgrade() -> None:
    """删除 open_platform_users 表。"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS open_platform_users CASCADE"))
    await engine.dispose()
    print("Migration complete: open_platform_users table dropped")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        asyncio.run(downgrade())
    else:
        asyncio.run(upgrade())
```

## Step 2: 在 UniData/models/open_platform.py 末尾添加模型

打开 `UniData/app/models/open_platform.py`，在文件末尾添加：

```python
class OpenPlatformUser(Base):
    """本地注册用户模型，支持启用/禁用状态管理。"""
    __tablename__ = "open_platform_users"

    id = Column(String, primary_key=True, nullable=False)
    username = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
```

## Step 3: 验证导入

确保 `OpenPlatformUser` 可以从 `app.models.open_platform` 导入：
```python
from app.models.open_platform import OpenPlatformUser  # 验证无报错
```

## Report File
`/Users/libiao/Desktop/github/pg2meili-cdc/.superpowers/sdd/user-management/task-1-report.md`
