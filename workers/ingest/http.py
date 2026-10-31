"""SSRF-guarded HTTP GET: per-hop IP checks, pinned connection, size and redirect limits."""

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from shared.security.url_guard import UrlRejected, check_url

MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
USER_AGENT = "AINewsPlatform/0.2 (personal news reader; excerpts and links only)"


class FetchError(RuntimeError):
    pass


@dataclass
class Response:
    status: int
    body: bytes
    etag: str | None
    last_modified: str | None
    not_modified: bool = False


def guarded_get(url: str, etag: str | None = None, last_modified: str | None = None,
                resolver=None, client: httpx.Client | None = None) -> Response:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml",
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    own_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=False)
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            try:
                checked = check_url(current, **({"resolver": resolver} if resolver else {}))
            except UrlRejected as error:
                raise FetchError(f"Blocked URL: {error}") from error
            parts = urlsplit(current)
            # Connect to the validated IP (prevents DNS rebinding); keep Host and SNI as the real name.
            netloc = f"[{checked.ip}]" if ":" in checked.ip else checked.ip
            if parts.port:
                netloc += f":{parts.port}"
            pinned = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
            request_headers = {**headers, "Host": parts.netloc}
            try:
                with client.stream("GET", pinned, headers=request_headers,
                                   extensions={"sni_hostname": checked.host}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("Redirect without a location.")
                        current = urljoin(current, location)
                        continue
                    if response.status_code == 304:
                        return Response(304, b"", etag, last_modified, not_modified=True)
                    if response.status_code != 200:
                        raise FetchError(f"Unexpected HTTP status {response.status_code}.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise FetchError("Response exceeded the 5 MB limit.")
                    return Response(200, bytes(body), response.headers.get("etag"),
                                    response.headers.get("last-modified"))
            except httpx.HTTPError as error:
                raise FetchError(f"Network error: {type(error).__name__}.") from error
        raise FetchError("Too many redirects.")
    finally:
        if own_client:
            client.close()
