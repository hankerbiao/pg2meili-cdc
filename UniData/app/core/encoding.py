"""Base64url（无填充）编解码助手，供签名 cookie 会话复用。

`admin_auth` 与 `oa_auth` 的 HMAC 签名 cookie 都需要「字节 ↔ URL 安全无填充 base64」
互转，原先各自复制了一份实现；抽到此处避免漂移。
"""
from __future__ import annotations

import base64


def b64encode(value: bytes) -> str:
    """字节 → URL 安全的无填充 base64 字符串。"""
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64decode(value: str) -> bytes:
    """无填充 base64url 字符串 → 字节（自动补齐 padding）。"""
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
