"""应用身份校验模块（基于 JWT）。

该模块的职责是：
1. 从 HTTP 请求头中提取并解析 JWT；
2. 使用配置中的 jwt_secret 对令牌进行 HS256 验签与过期检查；
3. 从令牌中解析出 app_name 和 scopes，封装为 AppIdentity 返回给业务层。

这样所有需要鉴权的接口只需依赖 get_current_app，就可以拿到统一的应用身份信息。
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import List, Optional

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


@dataclass
class AppIdentity:
    """表示当前请求对应的应用身份。

    - app_name: 应用名称，来自 JWT 中的 app_name 或 sub
    - scopes: 权限范围列表，用于控制调用方可以访问哪些能力
    """

    app_name: str
    scopes: List[str]


def _base64url_decode(data: str) -> bytes:
    """对 JWT 中使用的 base64url 字符串进行解码。

    JWT 规范规定结尾的 '=' 可以省略，因此这里需要补齐 padding。
    """
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _base64url_encode(data: bytes) -> str:
    """对数据进行 base64url 编码。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode_jwt(token: str, secret: str, algorithms: Optional[List[str]] = None) -> dict:
    """手动解析并验证一个使用 HS256 签名的 JWT。

    步骤：
    1. 拆分 header.payload.signature 三段；
    2. 解码并反序列化 header / payload；
    3. 检查签名算法是否在允许列表；
    4. 使用 jwt_secret 对 header.payload 重新计算签名并比对；
    5. 校验 exp 过期时间字段（如存在）。
    """
    if algorithms is None:
        algorithms = ["HS256"]

    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌格式",
        )

    header_b64, payload_b64, signature_b64 = parts

    try:
        header = json.loads(_base64url_decode(header_b64))
        payload = json.loads(_base64url_decode(payload_b64))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法解析令牌",
        )

    alg = header.get("alg")
    if alg not in algorithms:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="不支持的签名算法",
        )

    # 根据 header 和 payload 重新计算签名
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")

    # 使用恒定时间比较函数，避免时序攻击
    if not hmac.compare_digest(expected_sig_b64, signature_b64):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌签名无效",
        )

    # 如存在 exp 字段，按秒级时间戳校验是否过期
    exp = payload.get("exp")
    if exp is not None:
        try:
            exp_int = int(exp)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌过期时间无效",
            )
        now = int(time.time())
        if now >= exp_int:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌已过期",
            )

    return payload


async def get_current_app(
    authorization: str = Header(default="", alias="Authorization"),
    x_app_name: str = Header(default="", alias="X-App-Name"),
) -> AppIdentity:
    """从请求头中解析出当前调用方的应用身份。

    预期的请求头格式：
    - Authorization: Bearer <jwt>
    - X-App-Name: 可选，额外声明应用名，用于与 JWT 内容做一次交叉校验
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Authorization 头",
        )

    # 只接受标准 Bearer 令牌格式
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Authorization 格式",
        )

    settings = get_settings()
    secret = settings.jwt_secret

    payload = _decode_jwt(token, secret=secret, algorithms=["HS256"])

    # 从 payload 中提取应用名称
    app_name = payload.get("app_name") or payload.get("sub")
    if not app_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌中缺少 app_name",
        )

    # 如客户端额外传入 X-App-Name，则要求与 JWT 内部信息一致
    if x_app_name and x_app_name != app_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌与头部应用名称不匹配",
        )

    # scopes 可以是字符串（空格分隔）或列表，这里统一归一化为 List[str]
    scopes_raw = payload.get("scopes") or payload.get("scope") or []
    if isinstance(scopes_raw, str):
        scopes = [s for s in scopes_raw.split() if s]
    elif isinstance(scopes_raw, list):
        scopes = [str(s) for s in scopes_raw]
    else:
        scopes = []

    return AppIdentity(app_name=app_name, scopes=scopes)
