"""SSRF protection for outbound fetches (SECURITY.md section 4)."""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit


class UrlRejected(ValueError):
    """Raised when a URL must not be fetched."""


@dataclass(frozen=True)
class CheckedUrl:
    url: str
    host: str
    port: int
    ip: str


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or not address.is_global
    )


def check_url(url: str, resolver=socket.getaddrinfo) -> CheckedUrl:
    """Validate scheme, userinfo and resolved addresses; return a pinned IP to connect to."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise UrlRejected("Only http and https URLs are allowed.")
    if parts.username is not None or parts.password is not None:
        raise UrlRejected("URLs with credentials are not allowed.")
    host = parts.hostname
    if not host:
        raise UrlRejected("URL has no host.")
    port = parts.port or (443 if parts.scheme == "https" else 80)

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [literal]
    else:
        try:
            infos = resolver(host, port, type=socket.SOCK_STREAM)
        except OSError as error:
            raise UrlRejected("Host could not be resolved.") from error
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses:
        raise UrlRejected("Host could not be resolved.")
    # Every resolved address must be public, so a mixed DNS answer cannot smuggle one in.
    if not all(_is_public(address) for address in addresses):
        raise UrlRejected("Host resolves to a non-public address.")
    return CheckedUrl(url=url, host=host, port=port, ip=str(addresses[0]))
