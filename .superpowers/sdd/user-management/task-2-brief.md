# Task 2: 后端 — 用户管理 Model 和 Service

## Context
Task 1 completed and the `OpenPlatformUser` model is now available.

## Files
- Modify: `UniData/app/models/open_platform.py`
- Modify: `UniData/app/services/open_platform_service.py`

## Models already added (from Task 1)
```python
class OpenPlatformUser(Base):
    __tablename__ = "open_platform_users"

    id = Column(String, primary_key=True, nullable=False)
    username = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
```

## Step 1: Add service methods to OpenPlatformService

Open `UniData/app/services/open_platform_service.py` and add these methods to the class:

```python
@staticmethod
async def list_users(db: AsyncSession, user_status: str | None = None) -> list[OpenPlatformUser]:
    """列出所有本地注册用户。"""
    from sqlalchemy import select
    query = select(OpenPlatformUser).order_by(OpenPlatformUser.created_at.desc())
    if user_status:
        query = query.where(OpenPlatformUser.status == user_status)
    return list((await db.execute(query)).scalars().all())

@staticmethod
async def get_user(db: AsyncSession, user_id: str) -> OpenPlatformUser | None:
    """根据 ID 获取用户。"""
    return await db.get(OpenPlatformUser, user_id)

@staticmethod
async def get_user_by_username(db: AsyncSession, username: str) -> OpenPlatformUser | None:
    """根据用户名获取用户（用于登录验证）。"""
    from sqlalchemy import select
    return await db.scalar(select(OpenPlatformUser).where(OpenPlatformUser.username == username))

@staticmethod
async def create_user(
    db: AsyncSession,
    *,
    username: str,
    display_name: str,
    password_hash: str,
    actor: str,
    source_ip: str | None = None,
) -> OpenPlatformUser:
    """创建新用户。"""
    from sqlalchemy import select
    from fastapi import HTTPException, status
    existing = await db.scalar(select(OpenPlatformUser.id).where(OpenPlatformUser.username == username))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    
    user = OpenPlatformUser(
        id=uuid.uuid4().hex,
        username=username,
        display_name=display_name,
        password_hash=password_hash,
        status="active",
    )
    db.add(user)
    await db.flush()
    cls._add_outbox(db, user.id, "user.upsert", {"id": user.id, "username": user.username, "status": user.status})
    cls.add_audit(db, actor=actor, action="user.create", target_type="user", target_id=user.id, source_ip=source_ip)
    return user

@staticmethod
async def update_user_status(
    db: AsyncSession,
    user_id: str,
    new_status: str,
    actor: str,
    source_ip: str | None = None,
) -> OpenPlatformUser:
    """启用或禁用用户。"""
    from fastapi import HTTPException, status
    user = await db.get(OpenPlatformUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if new_status not in ("active", "disabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的状态值")
    user.status = new_status
    await db.flush()
    cls._add_outbox(db, user.id, "user.upsert", {"id": user.id, "username": user.username, "status": user.status})
    cls.add_audit(db, actor=actor, action=f"user.{new_status}", target_type="user", target_id=user.id, source_ip=source_ip)
    return user

@staticmethod
async def delete_user(
    db: AsyncSession,
    user_id: str,
    actor: str,
    source_ip: str | None = None,
) -> None:
    """删除用户。"""
    from fastapi import HTTPException, status
    user = await db.get(OpenPlatformUser, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    await db.delete(user)
    await db.flush()
    cls.add_audit(db, actor=actor, action="user.delete", target_type="user", target_id=user_id, source_ip=source_ip)
```

## Step 2: Add import

Make sure these imports exist at the top of `open_platform_service.py`:
```python
import uuid
from typing import TYPE_CHECKING
```

Add `OpenPlatformUser` to the import from models:
```python
from app.models.open_platform import ApiKey, OpenPlatformApp, OpenPlatformUser
```

## Step 3: Verify

Run: `python -c "from app.services.open_platform_service import open_platform_service; print('OK')"`

## Report File
`/Users/libiao/Desktop/github/pg2meili-cdc/.superpowers/sdd/user-management/task-2-report.md`
