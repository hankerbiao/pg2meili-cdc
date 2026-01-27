"""简单的 JWT 生成脚本，和 app.core.auth 使用相同的 HS256 签名方式。"""
import argparse
import base64
import hashlib
import hmac
import json
import time
from typing import List

from app.core.config import get_settings


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_jwt(app_name: str, scopes: List[str], ttl_seconds: int) -> str:
    settings = get_settings()
    secret = settings.jwt_secret

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "app_name": app_name,
        "scopes": scopes,
        "exp": int(time.time()) + ttl_seconds,
    }

    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate JWT for UniData apps")
    parser.add_argument("--app-name", required=True, help="应用名称，对应 JWT 中的 app_name")
    parser.add_argument(
        "--scopes",
        default="",
        help="以逗号分隔的权限列表，例如: testcases:write,indexes:read",
    )
    parser.add_argument(
        "--ttl",
        type=int,
        default=3600,
        help="令牌有效期（秒），默认 3600",
    )

    args = parser.parse_args()

    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]

    token = generate_jwt(args.app_name, scopes, args.ttl)
    print(token)


if __name__ == "__main__":
    main()

