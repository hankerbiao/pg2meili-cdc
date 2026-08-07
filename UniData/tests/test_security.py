"""SSRF 防护校验的单测：Agent 地址与 base_url 合法性。

注意：测试在隔离网络（无 DNS）下运行，域名解析相关用例通过 monkeypatch
socket.getaddrinfo 控制，避免依赖真实网络。
"""
from __future__ import annotations

import socket

import pytest

from app.core import security
from app.core.config import get_settings

# 用一个确定公开、不被 is_private 判定为私有的地址做正向用例。
PUBLIC_IP = "8.8.8.8"


@pytest.fixture
def no_allowlist(monkeypatch):
    monkeypatch.delenv("AGENT_ALLOWED_CIDRS", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def allow_private(monkeypatch):
    monkeypatch.setenv("AGENT_ALLOWED_CIDRS", "10.0.0.0/8")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_rejects_loopback(no_allowlist):
    with pytest.raises(ValueError):
        security.validate_agent_address("127.0.0.1", 8080)


def test_rejects_cloud_metadata(no_allowlist):
    with pytest.raises(ValueError):
        security.validate_agent_address("169.254.169.254", 80)


def test_rejects_link_local_ipv4(no_allowlist):
    with pytest.raises(ValueError):
        security.validate_agent_address("169.254.1.1", 8080)


def test_rejects_private_rfc1918(no_allowlist):
    with pytest.raises(ValueError):
        security.validate_agent_address("10.1.2.3", 8080)


def test_rejects_unspecified(no_allowlist):
    with pytest.raises(ValueError):
        security.validate_agent_address("0.0.0.0", 8080)


def test_accepts_public_address(no_allowlist):
    security.validate_agent_address(PUBLIC_IP, 8080)


def test_rejects_bad_port(no_allowlist):
    with pytest.raises(ValueError):
        security.validate_agent_address(PUBLIC_IP, 70000)


def test_allowed_cidr_permit_private(allow_private):
    # 白名单内的私网地址允许。
    security.validate_agent_address("10.1.2.3", 8080, allowed_cidrs=["10.0.0.0/8"])
    # 白名单外的受限地址仍拒绝。
    with pytest.raises(ValueError):
        security.validate_agent_address("192.168.1.1", 8080, allowed_cidrs=["10.0.0.0/8"])


def test_base_url_requires_http(no_allowlist):
    with pytest.raises(ValueError):
        security.validate_agent_base_url("ftp://10.0.0.1/")
    with pytest.raises(ValueError):
        security.validate_agent_base_url("file:///etc/passwd")


def test_base_url_rejects_credentials(no_allowlist):
    with pytest.raises(ValueError):
        security.validate_agent_base_url("http://user:pass@8.8.8.8/")


def test_base_url_rejects_restricted_host(no_allowlist):
    with pytest.raises(ValueError):
        security.validate_agent_base_url("http://127.0.0.1:8080/")
    with pytest.raises(ValueError):
        security.validate_agent_base_url("http://169.254.169.254/latest/meta-data/")


def test_base_url_ip_literal_allowed(no_allowlist):
    norm = security.validate_agent_base_url(f"https://{PUBLIC_IP}:9090/path?x=1#frag")
    assert norm == f"https://{PUBLIC_IP}:9090"


def test_base_url_domain_resolves_public(monkeypatch, no_allowlist):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port or 80))],
    )
    norm = security.validate_agent_base_url("https://agent.example.com:9090/path?x=1#frag")
    assert norm == "https://agent.example.com:9090"


def test_base_url_domain_resolves_private_rejected(monkeypatch, no_allowlist):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port or 80))],
    )
    with pytest.raises(ValueError):
        security.validate_agent_base_url("http://agent.internal/")


def test_base_url_normalizes_and_allows_none(no_allowlist):
    assert security.validate_agent_base_url("") is None
    assert security.validate_agent_base_url(None) is None
