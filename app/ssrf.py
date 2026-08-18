"""SSRF guard for source URLs submitted to /api/jobs.

The pipeline passes user-supplied URLs to yt-dlp / httpx / ffmpeg on Modal.
Without a guard, an authenticated user could point those tools at internal
infrastructure (cloud metadata endpoints like 169.254.169.254, localhost
services, or private-network hosts). This module resolves the hostname up
front and rejects private/reserved destinations.
"""

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

# RFC1918 + link-local + loopback + CGNAT + reserved + metadata + multicast.
_PRIVATE_NETS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local incl. cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved
    ipaddress.ip_network("255.255.255.255/32"),
)


def is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unresolvable/weird literal — treat as unsafe
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    return any(ip in net for net in _PRIVATE_NETS)


def _resolve_all(host: str) -> list[str]:
    """Resolve a hostname to all A records (best effort)."""
    try:
        return [entry[4][0] for entry in socket.getaddrinfo(host, 80)]
    except socket.gaierror:
        return []


def validate_source_url(url: str) -> Optional[str]:
    """Return an error string if the URL is dangerous, else None.

    Blocks:
      - non-http(s) schemes (file://, gopher://, ...)
      - literal private/loopback/link-local IPs
      - hostnames that resolve to any private/reserved IP
      - IP literals in the host portion (bypasses DNS-based checks below)
    """
    if not url:
        return "Source URL is required"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Unsupported URL scheme '{parsed.scheme or '(none)'}'"

    host = parsed.hostname
    if not host:
        return "URL has no hostname"

    # Literal IP in the URL — validate directly (avoids DNS rebinding races).
    try:
        ip = ipaddress.ip_address(host)
        if is_private_ip(str(ip)):
            return f"Private/reserved address blocked: {host}"
        return None
    except ValueError:
        pass  # hostname, fall through to DNS resolution

    resolved = _resolve_all(host)
    if not resolved:
        # Can't prove the destination is public — reject rather than let a
        # future DNS rebinding / internal alias slip through.
        return f"Could not resolve hostname: {host}"
    for ip_str in resolved:
        if is_private_ip(ip_str):
            return f"Hostname {host} resolves to private/reserved address {ip_str}"

    return None