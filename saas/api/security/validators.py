from __future__ import annotations

import ipaddress
import json
import socket
from typing import Optional
from urllib.parse import urlparse

import yaml

from api.config import settings

_PRIVATE_NETS = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("100.64.0.0/10"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("fe80::/10"),
]


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in _PRIVATE_NETS)
    except ValueError:
        return True


def validate_url(url: str) -> Optional[str]:
    """Returns an error string, or None if URL is safe to fetch."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "URL must use http or https"
    hostname = parsed.hostname
    if not hostname:
        return "URL is missing a hostname"
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return f"Cannot resolve hostname: {hostname}"
    for _, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        if _is_private_ip(ip):
            return f"URL resolves to a private/internal address ({ip}) — not allowed"
    return None


def validate_openapi_content(content: bytes) -> Optional[str]:
    """Returns an error string, or None if content looks like a valid OpenAPI spec."""
    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        return f"Content exceeds maximum allowed size ({settings.MAX_FILE_SIZE_MB} MB)"
    try:
        doc = yaml.safe_load(content)
    except Exception:
        try:
            doc = json.loads(content)
        except Exception:
            return "File is not valid YAML or JSON"
    if not isinstance(doc, dict):
        return "OpenAPI spec root must be an object"
    if "openapi" not in doc and "swagger" not in doc:
        return "File does not appear to be a valid OpenAPI/Swagger spec (missing 'openapi' or 'swagger' key)"
    if "paths" not in doc:
        return "OpenAPI spec must contain a 'paths' section"
    return None
