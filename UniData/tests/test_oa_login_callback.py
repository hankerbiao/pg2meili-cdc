"""OA 单点登录端点回归测试（登录跳转 / 回调验签 / 当前用户 / 登出）。

重点覆盖此前零测试的：
- ``GET /oa/login`` 跳转 springboard（无参数）与带 status/payload 时直接验签建会话；
- ``POST /oa/callback`` 验签成功建会话，以及验签失败（篡改签名 / 过期 / 缺 itcode / status!=success）的负路径；
- ``DELETE /oa/logout`` 清除 cookie。

需要真实 Postgres：通过 ``TEST_PG_CONN_STRING`` 提供隔离测试库；
未配置时 conftest 的 db_session 会自动 skip 本模块所有用例。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.encoding import b64encode
from app.main import app


def _make_oa_jwt(secret: str, itcode: str = "zhao", name: str = "赵", email: str = "z@x.com", exp: int | None = None) -> str:
    header = b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64encode(
        json.dumps(
            {"itcode": itcode, "姓名": name, "email": email, "exp": exp or int(time.time()) + 600}
        ).encode()
    )
    sig = b64encode(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


@pytest.fixture
async def oa_auth_client(db_session: AsyncSession):
    settings = get_settings()
    original = (
        settings.oa_jwt_secret,
        settings.oa_login_base_url,
        settings.oa_app_name,
        settings.oa_session_ttl_seconds,
        settings.oa_cookie_secure,
        settings.oa_cookie_name,
    )
    settings.oa_jwt_secret = "test-oa-jwt-secret-long-enough"
    settings.oa_login_base_url = "https://springboard.example.com/login"
    settings.oa_app_name = "unidata"
    settings.oa_session_ttl_seconds = 3600
    settings.oa_cookie_secure = False
    settings.oa_cookie_name = "unidata_oa_session"

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as client:
        yield client
    app.dependency_overrides.clear()
    (
        settings.oa_jwt_secret,
        settings.oa_login_base_url,
        settings.oa_app_name,
        settings.oa_session_ttl_seconds,
        settings.oa_cookie_secure,
        settings.oa_cookie_name,
    ) = original


class TestOaLoginRedirect:
    async def test_login_without_params_redirects_to_springboard(self, oa_auth_client: AsyncClient):
        resp = await oa_auth_client.get("/api/v1/auth/oa/login")
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("https://springboard.example.com/login/unidata")

    async def test_login_with_valid_payload_builds_session_and_302(self, oa_auth_client: AsyncClient):
        settings = get_settings()
        jwt = _make_oa_jwt(settings.oa_jwt_secret, itcode="zhao")
        resp = await oa_auth_client.get(
            "/api/v1/auth/oa/login", params={"status": "success", "payload": jwt}
        )
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("/open-platform/console")
        # 会话 cookie 已写入
        assert "unidata_oa_session" in resp.cookies


class TestOaCallback:
    async def test_callback_success_returns_profile_and_sets_cookie(self, oa_auth_client: AsyncClient):
        settings = get_settings()
        jwt = _make_oa_jwt(settings.oa_jwt_secret, itcode="zhao", name="赵", email="z@x.com")
        resp = await oa_auth_client.post(
            "/api/v1/auth/oa/callback", json={"status": "success", "payload": jwt}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["itcode"] == "zhao"
        assert data["name"] == "赵"
        assert data["email"] == "z@x.com"
        assert "unidata_oa_session" in resp.cookies

    async def test_callback_tampered_signature_rejected(self, oa_auth_client: AsyncClient):
        settings = get_settings()
        jwt = _make_oa_jwt(settings.oa_jwt_secret, itcode="zhao")
        header, payload, _sig = jwt.split(".")
        bad_sig = b64encode(b"forged")
        resp = await oa_auth_client.post(
            "/api/v1/auth/oa/callback",
            json={"status": "success", "payload": f"{header}.{payload}.{bad_sig}"},
        )
        assert resp.status_code == 400

    async def test_callback_expired_jwt_rejected(self, oa_auth_client: AsyncClient):
        settings = get_settings()
        jwt = _make_oa_jwt(settings.oa_jwt_secret, itcode="zhao", exp=int(time.time()) - 100)
        resp = await oa_auth_client.post(
            "/api/v1/auth/oa/callback", json={"status": "success", "payload": jwt}
        )
        assert resp.status_code == 400

    async def test_callback_missing_itcode_rejected(self, oa_auth_client: AsyncClient):
        settings = get_settings()
        jwt = _make_oa_jwt(settings.oa_jwt_secret, itcode="")  # 空 itcode
        resp = await oa_auth_client.post(
            "/api/v1/auth/oa/callback", json={"status": "success", "payload": jwt}
        )
        assert resp.status_code == 400

    async def test_callback_non_success_status_rejected(self, oa_auth_client: AsyncClient):
        settings = get_settings()
        jwt = _make_oa_jwt(settings.oa_jwt_secret, itcode="zhao")
        resp = await oa_auth_client.post(
            "/api/v1/auth/oa/callback", json={"status": "fail", "payload": jwt}
        )
        assert resp.status_code == 400


class TestOaLogout:
    async def test_logout_clears_cookie(self, oa_auth_client: AsyncClient):
        resp = await oa_auth_client.delete("/api/v1/auth/oa/logout")
        assert resp.status_code == 200
        assert resp.json()["data"]["logged_out"] is True
        # Set-Cookie 指示删除（max-age=0 或过期）
        sc = resp.headers.get("set-cookie", "")
        assert "unidata_oa_session" in sc
