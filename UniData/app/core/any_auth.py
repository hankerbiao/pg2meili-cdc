"""统一登录态：管理员会话与 OA 会话共用控制台。

设计：登录体系只有一套入口语义——任一有效会话（管理员密码登录的
``open_platform_session`` 或 OA 单点登录的 ``unidata_oa_session``）即可
进入控制台；按身份（role）区分可见内容与操作边界：

- admin：全部应用 / 代理节点 / 审计日志，全量操作。
- oa：仅能看到并操作 owner_itcode == 自己 itcode 的应用及其 API Key。

写操作 CSRF：管理员会话沿用 X-CSRF-Token 双 token 校验；OA 会话 Cookie
为 SameSite=Strict，天然防跨站请求伪造，故不再强制 CSRF Token。
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import SESSION_COOKIE, decode_admin_session
from app.core.config import get_settings
from app.core.database import get_db
from app.core.oa_auth import decode_oa_session
from app.models.oa import OaUser

ROLE_ADMIN = "admin"
ROLE_OA = "oa"


@dataclass(frozen=True)
class AnySession:
    role: Literal["admin", "oa"]
    username: str  # admin 时为管理员用户名，oa 时为工号 itcode
    name: str = ""
    email: str = ""
    csrf_token: str | None = None  # 仅 admin 会话有值


async def get_any_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AnySession:
    """任一有效会话即可；管理员优先（级别更高，身份以管理员为准）。

    注意：若管理员 cookie 存在但已过期/被篡改，decode_admin_session 会抛
    401，此时不再回退到 OA 会话，避免身份混淆。

    OA 用户若已被管理员禁用（oa_users.status == 'disabled'），即使持有有效
    会话也返回 401，拒绝其继续访问控制台（需重新登录才能生效；被禁后旧
    会话在新请求时即被拦截）。
    """
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        admin = decode_admin_session(token)
        return AnySession(
            role=ROLE_ADMIN,
            username=admin.username,
            name=admin.username,
            csrf_token=admin.csrf_token,
        )
    settings = get_settings()
    oa_token = request.cookies.get(settings.oa_cookie_name, "")
    if oa_token:
        oa = decode_oa_session(oa_token)
        user = await db.scalar(select(OaUser).where(OaUser.itcode == oa.itcode))
        if user is not None and getattr(user, "status", "active") == "disabled":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="该账号已被禁用，请联系管理员")
        return AnySession(role=ROLE_OA, username=oa.itcode, name=oa.name, email=oa.email)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录开放平台")


def require_any_csrf(
    identity: AnySession = Depends(get_any_session),
    csrf_token: str = Header(default="", alias="X-CSRF-Token"),
) -> AnySession:
    """写操作守卫：admin 需通过 X-CSRF-Token 校验；oa 会话（SameSite=Strict）跳过。"""
    if identity.role == ROLE_ADMIN:
        expected = identity.csrf_token or ""
        if not csrf_token or not hmac.compare_digest(csrf_token, expected):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败")
    return identity
