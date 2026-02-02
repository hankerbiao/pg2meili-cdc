---
name: fastapi-templates
description: Create production-ready FastAPI projects with async patterns, dependency injection, and comprehensive error handling. Use when building new FastAPI applications or setting up backend API projects.
---

# FastAPI Project Templates

Production-ready FastAPI project structures with async patterns, dependency injection, middleware, and best practices for building high-performance APIs.

## When to Use This Skill

- Starting new FastAPI projects from scratch
- Implementing async REST APIs with Python
- Building high-performance web services and microservices
- Creating async applications with PostgreSQL, MongoDB
- Setting up API projects with proper structure and testing

## Core Concepts

### 1. Project Structure

**Recommended Layout:**

```
app/
├── api/                    # API routes
│   ├── v1/
│   │   ├── endpoints/
│   │   │   ├── users.py
│   │   │   ├── auth.py
│   │   │   └── items.py
│   │   └── router.py
│   └── dependencies.py     # Shared dependencies
├── core/                   # Core configuration
│   ├── config.py
│   ├── security.py
│   └── database.py
├── models/                 # Database models
│   ├── user.py
│   └── item.py
├── schemas/                # Pydantic schemas
│   ├── user.py
│   └── item.py
├── services/               # Business logic
│   ├── user_service.py
│   └── auth_service.py
├── repositories/           # Data access
│   ├── user_repository.py
│   └── item_repository.py
└── main.py                 # Application entry
```

### 2. Dependency Injection

FastAPI's built-in DI system using `Depends`:

- Database session management
- Authentication/authorization
- Shared business logic
- Configuration injection

### 3. Async Patterns

Proper async/await usage:

- Async route handlers
- Async database operations
- Async background tasks
- Async middleware

## Implementation Patterns

### Pattern 1: Complete FastAPI Application

```python
# main.py
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession 
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    future=True
)

# 修改点：class_ 必须是 SQLModel 提供的 AsyncSession
SessionLocal = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# SQLModel 本身就是基类，通常直接使用 SQLModel 即可
# 如果需要自定义公共字段，可以保留这个 Base
class Base(SQLModel):
    pass

async def get_db() -> AsyncSession:
    """数据库会话依赖项"""
    async with SessionLocal() as session:
        try:
            yield session
            # 注意：在依赖项中自动 commit 需谨慎，
            # 某些场景下你可能希望在 Service 层控制 commit
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### Pattern 2: CRUD Repository Pattern

```python
# repositories/base_repository.py
from typing import Generic, TypeVar, Type, Optional, List
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from pydantic import BaseModel

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """CRUD操作的基类仓储"""

    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: int) -> Optional[ModelType]:
        """根据ID获取记录"""
        result = await db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalars().first()

    async def get_multi(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100
    ) -> List[ModelType]:
        """获取多条记录"""
        result = await db.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def create(
        self,
        db: AsyncSession,
        obj_in: CreateSchemaType
    ) -> ModelType:
        """创建新记录"""
        db_obj = self.model(**obj_in.dict())
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        db_obj: ModelType,
        obj_in: UpdateSchemaType
    ) -> ModelType:
        """更新记录"""
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, id: int) -> bool:
        """删除记录"""
        obj = await self.get(db, id)
        if obj:
            await db.delete(obj)
            return True
        return False

# repositories/user_repository.py
from app.repositories.base_repository import BaseRepository
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    """用户专属仓储"""

    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalars().first()

    async def is_active(self, db: AsyncSession, user_id: int) -> bool:
        """检查用户是否处于激活状态"""
        user = await self.get(db, user_id)
        return user.is_active if user else False

user_repository = UserRepository(User)

```

### Pattern 3: Service Layer

```python
# services/user_service.py
from typing import Optional
from sqlmodel.ext.asyncio.session import AsyncSession
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate, User
from app.core.security import get_password_hash, verify_password

class UserService:
    """用户业务逻辑层"""

    def __init__(self):
        self.repository = user_repository

    async def create_user(
        self,
        db: AsyncSession,
        user_in: UserCreate
    ) -> User:
        """创建新用户（密码已加密）"""
        # 检查邮箱是否已存在
        existing = await self.repository.get_by_email(db, user_in.email)
        if existing:
            raise ValueError("Email already registered")

        # 加密密码
        user_in_dict = user_in.dict()
        user_in_dict["hashed_password"] = get_password_hash(user_in_dict.pop("password"))

        # 创建用户
        user = await self.repository.create(db, UserCreate(**user_in_dict))
        return user

    async def authenticate(
        self,
        db: AsyncSession,
        email: str,
        password: str
    ) -> Optional[User]:
        """用户身份验证"""
        user = await self.repository.get_by_email(db, email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def update_user(
        self,
        db: AsyncSession,
        user_id: int,
        user_in: UserUpdate
    ) -> Optional[User]:
        """更新用户"""
        user = await self.repository.get(db, user_id)
        if not user:
            return None

        if user_in.password:
            user_in_dict = user_in.dict(exclude_unset=True)
            user_in_dict["hashed_password"] = get_password_hash(
                user_in_dict.pop("password")
            )
            user_in = UserUpdate(**user_in_dict)

        return await self.repository.update(db, user, user_in)

user_service = UserService()

```

### Pattern 4: API Endpoints with Dependencies

```python
# api/v1/endpoints/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List

from app.core.database import get_db
from app.models.user import User 
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import user_service
from app.api.dependencies import get_current_user

router = APIRouter()

@router.post("/", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新用户"""
    try:
        user = await user_service.create_user(db, user_in)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/me", response_model=User)
async def read_current_user(
    current_user: User = Depends(get_current_user)
):
    """获取当前用户"""
    return current_user

@router.get("/{user_id}", response_model=User)
async def read_user(
    user_id: int,
    db: AsyncSession = Depends(get_db), # 使用 SQLModel 的 AsyncSession
    current_user: User = Depends(get_current_user)
):
    """根据ID获取用户"""
    user = await user_service.repository.get(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.patch("/{user_id}", response_model=User)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新用户"""
    # 权限检查：只能修改自己的信息
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    user = await user_service.update_user(db, user_id, user_in)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除用户"""
    # 权限检查：只能删除自己的账户
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    deleted = await user_service.repository.delete(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
```

### Pattern 5: Authentication & Authorization

```python
# core/security.py
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建JWT访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码与哈希值是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """对密码进行哈希处理"""
    return pwd_context.hash(password)

# api/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ALGORITHM
from app.core.config import get_settings
from app.repositories.user_repository import user_repository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """获取当前已认证的用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await user_repository.get(db, user_id)
    if user is None:
        raise credentials_exception

    return user
```

## Testing

```python
# tests/conftest.py
import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.main import app
from app.core.database import get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环（会话级别）"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_session():
    """创建测试数据库会话"""
    # 创建异步引擎
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)

    # 使用 SQLModel 的 metadata 创建表
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # 构造异步 Session 工厂，显式指定 class_=AsyncSession
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        yield session

    # 测试完成后清理资源（可选，内存数据库会自动销毁）
    await engine.dispose()

@pytest.fixture
async def client(db_session: AsyncSession):
    """创建测试客户端"""
    # 覆盖 FastAPI 的依赖项注入
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    # 测试结束后清除覆盖
    app.dependency_overrides.clear()
```

## Resources

- **references/fastapi-architecture.md**: Detailed architecture guide
- **references/async-best-practices.md**: Async/await patterns
- **references/testing-strategies.md**: Comprehensive testing guide
- **assets/project-template/**: Complete FastAPI project
- **assets/docker-compose.yml**: Development environment setup

## Best Practices

1. **Async All The Way**: Use async for database, external APIs
2. **Dependency Injection**: Leverage FastAPI's DI system
3. **Repository Pattern**: Separate data access from business logic
4. **Service Layer**: Keep business logic out of routes
5. **Pydantic Schemas**: Strong typing for request/response
6. **Error Handling**: Consistent error responses
7. **Testing**: Test all layers independently

## Common Pitfalls

- **Blocking Code in Async**: Using synchronous database drivers
- **No Service Layer**: Business logic in route handlers
- **Missing Type Hints**: Loses FastAPI's benefits
- **Ignoring Sessions**: Not properly managing database sessions
- **No Testing**: Skipping integration tests
- **Tight Coupling**: Direct database access in routes
