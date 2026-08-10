"""OA 单点登录端点：登录跳转、回调验签、当前用户与登出。"""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.response import ApiResponse, ok
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.oa_auth import (
    OaSession,
    create_oa_session,
    decode_and_verify_oa_jwt,
    get_oa_user,
)
from app.services.oa_service import assert_oa_user_active, get_oa_user_profile, upsert_oa_user

logger = logging.getLogger("unidata.oa")

router = APIRouter(prefix="/oa")


def set_oa_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """写入 OA 单点登录会话 cookie（双模登录与回调共用，避免重复配置）。"""
    response.set_cookie(
        settings.oa_cookie_name,
        token,
        max_age=settings.oa_session_ttl_seconds,
        httponly=True,
        secure=settings.oa_cookie_secure,
        samesite="strict",
        path="/",
    )


class OaCallbackRequest(BaseModel):
    status: str
    payload: str
    next: str | None = None


class OaUserResponse(BaseModel):
    itcode: str
    name: str
    email: str


@router.get("/login", summary="OA 登录：跳转 springboard 或处理 springboard 回调")
async def oa_login(
    response: Response,
    db: AsyncSession = Depends(get_db),
    status_value: str | None = Query(default=None, alias="status"),
    payload: str | None = Query(default=None),
    next_url: str | None = Query(default=None, alias="next"),
) -> Response:
    """双模端点：

    - 无 status/payload：将浏览器重定向到 springboard 登录代理（登录入口）。
    - 带 status/payload（springboard 平台侧 app_login_url 指向本端点时回跳到这里）：
      直接完成验签、建会话，302 到前端 OA 首页，避免 302 循环。
    """
    settings = get_settings()

    if status_value is not None or payload is not None:
        if status_value == "success" and payload:
            if not settings.oa_jwt_secret:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OA JWT 密钥未配置")
            try:
                decoded = decode_and_verify_oa_jwt(payload, settings.oa_jwt_secret)
            except HTTPException as exc:
                # 验签失败：不记录 payload（含用户敏感信息），跳回登录页并带错误标记
                logger.warning("OA 登录验签失败: %s", exc.detail)
                return RedirectResponse(url="/open-platform/login?oa=error", status_code=302)
            itcode = decoded.get("itcode")
            if not itcode:
                logger.warning("OA payload 缺少 itcode")
                return RedirectResponse(url="/open-platform/login?oa=error", status_code=302)
            try:
                await upsert_oa_user(db, itcode=str(itcode), profile=decoded)
                token, session = create_oa_session(itcode=str(itcode), profile=decoded)
            except Exception:  # noqa: BLE001 - 兜底：DB/会话异常时回登录页，避免 500 暴露内部错误
                logger.exception("OA 登录建会话失败")
                return RedirectResponse(url="/open-platform/login?oa=error", status_code=302)
            # 统一登录体系：OA 登录成功后进入同一控制台（按身份渲染不同内容）
            redirect = RedirectResponse(url="/open-platform/console", status_code=302)
            set_oa_session_cookie(redirect, token, settings)
            return redirect
        # status != success 或缺失 payload → 登录失败，回登录页并带错误标记
        logger.warning("OA 登录中止: status=%s payload_present=%s", status_value, bool(payload))
        return RedirectResponse(url="/open-platform/login?oa=error", status_code=302)

    # 普通登录入口：302 到 springboard，next 需 URL 编码
    callback = next_url or f"{settings.oa_login_base_url}/{settings.oa_app_name}"
    redirect_url = f"{settings.oa_login_base_url}/{settings.oa_app_name}?next={quote(callback, safe='')}"
    return Response(status_code=status.HTTP_302_FOUND, headers={"Location": redirect_url})


@router.post("/callback", summary="OA 登录回调：验签并建会话")
async def oa_callback(
    body: OaCallbackRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[OaUserResponse]:
    settings = get_settings()
    if body.status != "success":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OA 登录失败")
    if not settings.oa_jwt_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OA JWT 密钥未配置")
    payload = decode_and_verify_oa_jwt(body.payload, settings.oa_jwt_secret)
    itcode = payload.get("itcode")
    if not itcode:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OA 登录信息缺少 itcode")
    await upsert_oa_user(db, itcode=str(itcode), profile=payload)
    token, session = create_oa_session(itcode=str(itcode), profile=payload)
    set_oa_session_cookie(response, token, settings)
    return ok(OaUserResponse(itcode=session.itcode, name=session.name, email=session.email))


@router.get("/me", summary="获取当前 OA 用户")
async def oa_me(
    session: OaSession = Depends(get_oa_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    await assert_oa_user_active(db, session.itcode)
    profile = await get_oa_user_profile(db, session.itcode) or {}
    return ok(
        {
            "itcode": session.itcode,
            "name": session.name,
            "email": session.email,
            "profile": profile,
        }
    )


@router.delete("/logout", summary="OA 登出")
async def oa_logout(response: Response) -> ApiResponse[dict[str, bool]]:
    settings = get_settings()
    response.delete_cookie(settings.oa_cookie_name, path="/")
    return ok({"logged_out": True})
