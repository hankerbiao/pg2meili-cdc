"""any_auth 统一登录入口单元测试（无需 DB / 真实会话）。

mock 掉 admin/oa 会话解码与 OA 用户活跃校验，验证关键不变量：
- 无会话 -> 401；
- 管理员 cookie 优先（级别更高）；
- 管理员 cookie 损坏不锁死，回退 OA（P0-3）；
- OA 用户被禁用 -> 401 拦截；
- 写操作 CSRF：admin 强制、oa 会话（SameSite=Strict）跳过。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.core import any_auth
from app.core.any_auth import ROLE_ADMIN, ROLE_OA, AnySession, get_any_session, require_any_csrf


class _Req:
    def __init__(self, cookies: dict[str, str]):
        self.cookies = cookies


def _admin_session(username="admin", csrf="csrf-abc"):
    return SimpleNamespace(username=username, csrf_token=csrf)  # type: ignore[attr-defined]


def _oa_session(itcode="zhao", name="赵", email="z@x.com"):
    return SimpleNamespace(itcode=itcode, name=name, email=email)  # type: ignore[attr-defined]


async def test_no_session_raises_401():
    with patch.object(any_auth, "decode_admin_session", side_effect=HTTPException(401)), patch.object(
        any_auth, "decode_oa_session", side_effect=KeyError("no")
    ):
        with pytest.raises(HTTPException) as exc:
            await get_any_session(_Req({}), db=None)
    assert exc.value.status_code == 401


async def test_admin_cookie_takes_priority():
    with patch.object(any_auth, "decode_admin_session", return_value=_admin_session()), patch.object(
        any_auth, "decode_oa_session", return_value=_oa_session()
    ) as oa_decode:
        sess = await get_any_session(_Req({"open_platform_session": "tok"}), db=None)
    assert sess.role == ROLE_ADMIN
    assert sess.username == "admin"
    assert sess.csrf_token == "csrf-abc"
    oa_decode.assert_not_called()  # 管理员命中后不再解析 OA cookie


async def test_broken_admin_cookie_falls_back_to_oa():
    with patch.object(any_auth, "decode_admin_session", side_effect=HTTPException(401)), patch.object(
        any_auth, "decode_oa_session", return_value=_oa_session(itcode="qian")
    ), patch.object(any_auth, "assert_oa_user_active", new=any_auth_assert_ok()):
        sess = await get_any_session(_Req({"open_platform_session": "bad", "unidata_oa_session": "o"}), db=None)
    assert sess.role == ROLE_OA
    assert sess.username == "qian"


async def test_oa_user_disabled_blocked_401():
    with patch.object(any_auth, "decode_admin_session", side_effect=HTTPException(401)), patch.object(
        any_auth, "decode_oa_session", return_value=_oa_session(itcode="sun")
    ), patch.object(any_auth, "assert_oa_user_active", new=any_auth_assert_fail()):
        with pytest.raises(HTTPException) as exc:
            await get_any_session(_Req({"unidata_oa_session": "o"}), db=None)
    assert exc.value.status_code == 401


async def test_oa_session_ok_returns_oa_role():
    with patch.object(any_auth, "decode_admin_session", side_effect=HTTPException(401)), patch.object(
        any_auth, "decode_oa_session", return_value=_oa_session(itcode="li", name="李", email="l@x.com")
    ), patch.object(any_auth, "assert_oa_user_active", new=any_auth_assert_ok()):
        sess = await get_any_session(_Req({"unidata_oa_session": "o"}), db=None)
    assert sess.role == ROLE_OA
    assert sess.username == "li"
    assert sess.name == "李"
    assert sess.email == "l@x.com"


def test_require_csrf_admin_missing_token_forbidden():
    ident = AnySession(role=ROLE_ADMIN, username="admin", csrf_token="expect")
    with pytest.raises(HTTPException) as exc:
        require_any_csrf(identity=ident, csrf_token="")
    assert exc.value.status_code == 403


def test_require_csrf_admin_wrong_token_forbidden():
    ident = AnySession(role=ROLE_ADMIN, username="admin", csrf_token="expect")
    with pytest.raises(HTTPException) as exc:
        require_any_csrf(identity=ident, csrf_token="wrong")
    assert exc.value.status_code == 403


def test_require_csrf_admin_correct_token_passes():
    ident = AnySession(role=ROLE_ADMIN, username="admin", csrf_token="expect")
    out = require_any_csrf(identity=ident, csrf_token="expect")
    assert out is ident


def test_require_csrf_oa_session_skips():
    ident = AnySession(role=ROLE_OA, username="zhou", name="周")
    # OA 会话无需 CSRF，即使传空也放行
    out = require_any_csrf(identity=ident, csrf_token="")
    assert out is ident


def any_auth_assert_ok():
    async def _ok(db, itcode):
        return None

    return _ok


def any_auth_assert_fail():
    async def _fail(db, itcode):
        raise HTTPException(status_code=401, detail="disabled")

    return _fail
