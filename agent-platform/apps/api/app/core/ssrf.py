"""Outbound URL guard: blocks private, loopback and link-local targets unless allow-listed."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.enums import ErrorCode
from app.core.errors import AppError


class OutboundBlocked(AppError):
    code = ErrorCode.ssrf_blocked


def _allowlisted(host: str, ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address]) -> bool:
    for entry in get_settings().outbound_allowlist:
        entry = entry.strip()
        if not entry:
            continue
        if entry.lower() == host.lower():
            return True
        try:
            net = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        if any(ip in net for ip in ips):
            return True
    return False


def _is_private(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified


async def guard_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise OutboundBlocked("Only http and https URLs are allowed", details={"url": url})
    host = parts.hostname
    if not host:
        raise OutboundBlocked("URL has no host", details={"url": url})
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)
        ips = [ipaddress.ip_address(info[4][0]) for info in infos]
    except (socket.gaierror, ValueError) as exc:
        raise OutboundBlocked(f"Cannot resolve host {host}", details={"host": host}) from exc
    if _allowlisted(host, ips):
        return
    blocked = [str(ip) for ip in ips if _is_private(ip)]
    if blocked:
        raise OutboundBlocked(
            "Destination resolves to a private or reserved address. Add it to OUTBOUND_ALLOWLIST to allow it.",
            details={"host": host, "addresses": blocked},
        )
