"""Parse RSS/Atom feeds into normalised item records (LLD section 3.3)."""

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from defusedxml import ElementTree

EXCERPT_MAX = 2000
TITLE_MAX = 300
TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$|cmp$)", re.I)
TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


@dataclass
class Item:
    title: str
    url: str
    author: str | None
    excerpt: str
    published_at: datetime | None
    title_hash: str
    image_url: str | None = None


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = TAG.sub(" ", html.unescape(value))
    return SPACE.sub(" ", TAG.sub(" ", html.unescape(text))).strip()


def canonical_url(url: str) -> str | None:
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING.match(k)])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, query, ""))


def normalise_title(title: str) -> str:
    return SPACE.sub(" ", re.sub(r"[^a-z0-9 ]", "", title.lower())).strip()


def title_hash(title: str) -> str:
    return hashlib.sha256(normalise_title(title).encode()).hexdigest()


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text(node, *names: str) -> str | None:
    for child in node:
        if _local(child.tag) in names and (child.text or "").strip():
            return child.text.strip()
    return None


IMG_SRC = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)
IMAGE_EXT = re.compile(r"\.(jpe?g|png|webp|gif|avif)(\?|$)", re.I)


def safe_image(url: str | None) -> str | None:
    """Only absolute https image URLs under 500 characters are kept."""
    if not url:
        return None
    url = html.unescape(url.strip())
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or len(url) > 500:
        return None
    return url


def find_image(node, *html_blobs: str | None) -> str | None:
    """Prefer media:content/thumbnail and image enclosures, then the first <img> in the markup."""
    for child in node:
        name = _local(child.tag)
        if name in {"content", "thumbnail"} and child.get("url"):
            kind = (child.get("type") or "") + (child.get("medium") or "")
            if name == "thumbnail" or "image" in kind or IMAGE_EXT.search(child.get("url", "")):
                if found := safe_image(child.get("url")):
                    return found
        if name in {"enclosure", "link"} and child.get("rel", "enclosure") == "enclosure":
            if (child.get("type") or "").startswith("image/") and (found := safe_image(child.get("url") or child.get("href"))):
                return found
    for blob in html_blobs:
        if blob and (match := IMG_SRC.search(html.unescape(blob))):
            if found := safe_image(match.group(1)):
                return found
    return None


def _make_item(title, link, author, summary, published, image=None) -> Item | None:
    title = strip_html(title)[:TITLE_MAX]
    link = canonical_url(link or "")
    if not title or not link:
        return None
    excerpt = strip_html(summary)
    if len(excerpt) > EXCERPT_MAX:
        excerpt = excerpt[: EXCERPT_MAX - 1].rstrip() + "…"
    return Item(title, link, strip_html(author) or None, excerpt, parse_date(published), title_hash(title), image)


def parse_feed(xml_bytes: bytes) -> list[Item]:
    """Parse RSS 2.0 or Atom. defusedxml rejects entity-expansion and external-entity attacks."""
    root = ElementTree.fromstring(xml_bytes, forbid_dtd=True)
    items: list[Item] = []
    if _local(root.tag) == "feed":
        for entry in root:
            if _local(entry.tag) != "entry":
                continue
            link = None
            for child in entry:
                if _local(child.tag) == "link" and child.get("rel", "alternate") == "alternate":
                    link = child.get("href")
                    break
            author = None
            for child in entry:
                if _local(child.tag) == "author":
                    author = _text(child, "name")
                    break
            item = _make_item(_text(entry, "title"), link, author,
                              _text(entry, "summary", "content"), _text(entry, "published", "updated"),
                              find_image(entry, _text(entry, "summary", "content")))
            if item:
                items.append(item)
    else:
        for node in root.iter():
            if _local(node.tag) != "item":
                continue
            item = _make_item(_text(node, "title"), _text(node, "link"), _text(node, "creator", "author"),
                              _text(node, "description", "summary"), _text(node, "pubDate", "date"),
                              find_image(node, _text(node, "encoded"), _text(node, "description")))
            if item:
                items.append(item)
    return items
