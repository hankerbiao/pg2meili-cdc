"""encoding 助手单元测试（纯函数，无依赖）。"""
from __future__ import annotations

import base64

from app.core.encoding import b64decode, b64encode


def test_roundtrip_preserves_bytes():
    data = b"hello \xe4\xb8\xad\xe6\x96\x87"
    assert b64decode(b64encode(data)) == data


def test_output_is_urlsafe_and_unpadded():
    enc = b64encode(b"any bytes here")
    assert "=" not in enc  # 无填充
    # 必须是标准 base64url 字符集
    base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4))
    assert "/" not in enc
    assert "+" not in enc


def test_empty_roundtrip():
    assert b64decode(b64encode(b"")) == b""


def test_matches_manual_reference():
    raw = b"x"
    ref = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    assert b64encode(raw) == ref
