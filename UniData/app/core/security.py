"""服务端主动请求 Agent 端点的安全校验（SSRF 防护）。

中心服务会对 Agent 自报的 ip:port / base_url 发起健康检查或下发指令，
若这些地址由调用方控制且未加校验，攻击者可借中心服务的网络位置探测内网、
云元数据服务等受限目标。本模块统一提供地址与 URL 的合法性校验。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import get_settings

# 云元数据地址（AWS/GCP/Azure/阿里云/腾讯云等通用 169.254.169.254）。
_METADATA_ADDRESSES = frozenset({ipaddress.ip_address("169.254.169.254")})


def _is_restricted(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """受限地址：回环 / 链路本地 / 组播 / 未指定 / 云元数据 / 私网。"""
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip in _METADATA_ADDRESSES
        or ip.is_private
    )


def _parse_cidrs(cidrs: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw in cidrs:
        raw = (raw or "").strip()
        if not raw:
            continue
        try:
            nets.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            # 非法 CIDR 直接忽略，不留白名单缺口。
            continue
    return nets


def _in_allowed(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, allowed: list) -> bool:
    return any(addr in net for net in allowed)


def validate_agent_address(
    ip: str,
    port: int,
    *,
    allowed_cidrs: list[str] | None = None,
) -> None:
    """校验 Agent 上报的 ip:port 是否可被中心安全访问。

    拒绝：格式非法、非 IP 文本、端口越界、受限地址（回环/链路本地/元数据/
    私网/组播/未指定）。除非该地址落在 allowed_cidrs 显式白名单内。
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError(f"非法的 Agent IP 地址: {ip!r}")
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError(f"非法的 Agent 端口: {port}")
    allowed = _parse_cidrs(allowed_cidrs or [])
    if _in_allowed(addr, allowed):
        return
    if _is_restricted(addr):
        raise ValueError(f"拒绝访问受限地址 {ip}:{port}（可能为内网/元数据/回环地址）")


def _check_host(
    host: str,
    port: int | None,
    *,
    allowed_cidrs: list[str] | None,
) -> None:
    """校验主机（可能是域名），DNS 解析后对所有结果二次校验，防 DNS rebinding。"""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None:
        _validate_one(addr, allowed_cidrs)
        return

    allowed = _parse_cidrs(allowed_cidrs or [])
    try:
        infos = socket.getaddrinfo(host, port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"无法解析 base_url 主机 {host!r}: {exc}")
    if not infos:
        raise ValueError(f"base_url 主机无可解析地址: {host!r}")
    for info in infos:
        resolved = ipaddress.ip_address(info[4][0])
        if _in_allowed(resolved, allowed):
            continue
        if _is_restricted(resolved):
            raise ValueError(f"base_url 解析到受限地址 {resolved}（来自 {host}）")


def _validate_one(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, allowed_cidrs: list[str] | None) -> None:
    allowed = _parse_cidrs(allowed_cidrs or [])
    if _in_allowed(addr, allowed):
        return
    if _is_restricted(addr):
        raise ValueError(f"拒绝访问受限地址 {addr}")


def validate_agent_base_url(
    raw: str | None,
    *,
    allowed_cidrs: list[str] | None = None,
) -> str | None:
    """规范化并校验 Agent 的 base_url，返回规范化结果或 None。

    仅允许 http/https；禁止 userinfo；解析主机并对所有解析地址二次校验。
    规范化后仅保留 scheme://host[:port]，去掉路径/查询/片段，避免重定向跳板。
    """
    if not raw:
        return None
    try:
        parsed = urlparse(raw.strip())
    except ValueError:
        raise ValueError(f"非法的 base_url: {raw!r}")
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"base_url 必须使用 http/https 协议: {raw!r}")
    if parsed.username or parsed.password:
        raise ValueError(f"base_url 禁止携带用户凭据: {raw!r}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"base_url 缺少主机: {raw!r}")
    port = parsed.port
    _check_host(host, port, allowed_cidrs=allowed_cidrs)

    norm = f"{parsed.scheme}://{host}"
    if port is not None:
        norm += f":{port}"
    return norm


def allowed_agent_cidrs() -> list[str]:
    """从配置读取可选的 Agent 私网白名单（逗号分隔 CIDR）。"""
    raw = (get_settings().agent_allowed_cidrs or "").strip()
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]
