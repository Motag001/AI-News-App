"""Ingestion runner: fetch active sources, normalise, group into stories, score."""

import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from api.store import connection
from shared.config.registry import Source, load_registry
from workers.ingest.http import FetchError, guarded_get
from workers.ingest.normalise import Item, parse_feed
from workers.intelligence.classify import classify
from workers.intelligence.dedup import find_story
from workers.intelligence.scoring import credibility_score, importance_score
from shared.categories import CATEGORY_WEIGHTS

log = logging.getLogger("ingest")

BACKFILL_DAYS = 7          # DATA_SOURCES.md section 5
MAX_ITEMS_PER_RUN = 30     # newest items per source per run
RESCORE_DAYS = 30
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))  # stories older than this are deleted
NEUTRAL_REACH = 0.5        # no reach metrics are available from feeds
DOMAIN_GAP_SECONDS = int(os.getenv("INGEST_DOMAIN_GAP_SECONDS", "10"))  # 1 request per 10 s per domain by default
_last_request_by_host: dict[str, float] = {}


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def extractive_summary(excerpt: str, max_words: int = 80) -> str:
    """First sentences of the source's own excerpt, up to 80 words. Not AI-generated."""
    words = excerpt.split()
    if len(words) <= max_words:
        return excerpt
    clipped = " ".join(words[:max_words])
    sentence_end = max(clipped.rfind(". "), clipped.rfind("? "), clipped.rfind("! "))
    return clipped[: sentence_end + 1] if sentence_end > 120 else clipped.rstrip(",;: ") + "…"


def sync_sources(database, sources: list[Source]) -> None:
    for source in sources:
        database.execute(
            """INSERT INTO source (id, name, type, tier, url, attribution) VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, type=excluded.type, tier=excluded.tier,
               url=excluded.url, attribution=excluded.attribution""",
            (source.id, source.name, source.type, source.tier, source.url, source.attribution),
        )


def store_items(database, source: Source, items: list[Item], now: datetime) -> int:
    cutoff = now - timedelta(days=BACKFILL_DAYS)
    fresh = [item for item in items if item.published_at is None or item.published_at >= cutoff]
    fresh.sort(key=lambda item: item.published_at or now, reverse=True)
    created = 0
    since = iso(now - timedelta(hours=72))
    for item in reversed(fresh[:MAX_ITEMS_PER_RUN]):
        if database.execute(
            "SELECT 1 FROM item WHERE source_id = ? AND canonical_url = ?", (source.id, item.url)
        ).fetchone():
            if item.image_url:
                database.execute(
                    "UPDATE item SET image_url = ? WHERE source_id = ? AND canonical_url = ? AND image_url IS NULL",
                    (item.image_url, source.id, item.url),
                )
            continue
        story_id = find_story(database, item.url, item.title_hash, item.title, since)
        published = item.published_at or now
        if story_id is None:
            category, confidence = classify(item.title, item.excerpt, source.category_hint)
            story_id = f"s-{uuid.uuid4().hex[:16]}"
            database.execute(
                """INSERT INTO story (id, canonical_title, category, category_confidence, summary_text,
                   credibility, importance, published_at, first_seen_at) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)""",
                (story_id, item.title, category, confidence, extractive_summary(item.excerpt),
                 iso(published), iso(now)),
            )
        database.execute(
            """INSERT INTO item (source_id, story_id, title, author, canonical_url, excerpt,
               published_at, fetched_at, title_hash, image_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source.id, story_id, item.title, item.author, item.url, item.excerpt,
             iso(item.published_at) if item.published_at else None, iso(now), item.title_hash, item.image_url),
        )
        created += 1
    return created


def rescore(database, now: datetime) -> None:
    """Recompute credibility, importance and representative fields from each story's items."""
    since = iso(now - timedelta(days=RESCORE_DAYS))
    for story in database.execute("SELECT id, category FROM story WHERE published_at >= ?", (since,)).fetchall():
        rows = database.execute(
            """SELECT i.title, i.excerpt, i.author, i.published_at, i.image_url, s.id AS source_id, s.tier
               FROM item i JOIN source s ON s.id = i.source_id WHERE i.story_id = ?
               ORDER BY s.tier, COALESCE(i.published_at, i.fetched_at)""",
            (story["id"],),
        ).fetchall()
        if not rows:
            continue
        distinct = {row["source_id"] for row in rows}
        credibility = credibility_score(
            [row["tier"] for row in rows],
            len(distinct),
            any(row["author"] for row in rows),
            any(row["published_at"] for row in rows),
        )
        dated = [row["published_at"] for row in rows if row["published_at"]]
        published = min(dated) if dated else iso(now)
        importance = importance_score(
            datetime.fromisoformat(published), NEUTRAL_REACH, credibility, story["category"], now
        )
        lead = rows[0]  # lowest tier (most primary) source supplies title and summary
        summary = extractive_summary(max((row["excerpt"] for row in rows if row["tier"] == lead["tier"]),
                                         key=len, default=""))
        database.execute(
            """UPDATE story SET credibility = ?, importance = ?, published_at = ?, canonical_title = ?,
               summary_text = ?, image_url = ? WHERE id = ?""",
            (credibility, importance, published, lead["title"], summary,
             next((row["image_url"] for row in rows if row["image_url"]), None), story["id"]),
        )


def purge_expired(database, now: datetime, days: int | None = None) -> int:
    """Delete stories older than the retention period; their items go with them (ON DELETE CASCADE)."""
    cutoff = iso(now - timedelta(days=days if days is not None else RETENTION_DAYS))
    deleted = database.execute("DELETE FROM story WHERE datetime(published_at) < datetime(?)", (cutoff,)).rowcount
    if deleted:
        log.info("purged %d stories older than the retention period", deleted)
    return deleted


def due_sources(database, sources: list[Source], now: datetime) -> list[Source]:
    due = []
    for source in sources:
        if source.status != "active":
            continue
        row = database.execute("SELECT next_run_at FROM source WHERE id = ?", (source.id,)).fetchone()
        if row is None or row["next_run_at"] is None or row["next_run_at"] <= iso(now):
            due.append(source)
    return due


def ingest_source(source: Source, now: datetime | None = None, fetch=guarded_get) -> str:
    """Fetch one source and persist the result. Returns a status string."""
    now = now or datetime.now(timezone.utc)
    with connection() as database:
        state = database.execute("SELECT etag, last_modified, consecutive_failures FROM source WHERE id = ?",
                                 (source.id,)).fetchone()
        started = iso(now)
        run_id = database.execute(
            "INSERT INTO run_record (source_id, started_at, status) VALUES (?, ?, 'running')", (source.id, started)
        ).lastrowid
    host = re.sub(r"^https?://([^/]+).*$", r"\1", source.url)
    wait = DOMAIN_GAP_SECONDS - (time.monotonic() - _last_request_by_host.get(host, -1e9))
    if wait > 0:
        time.sleep(wait)
    _last_request_by_host[host] = time.monotonic()

    status, error_code, created, etag, modified = "ok", None, 0, state["etag"], state["last_modified"]
    parsed: list[Item] = []
    try:
        response = fetch(source.url, state["etag"], state["last_modified"])
        if response.not_modified:
            status = "not_modified"
        else:
            etag, modified = response.etag, response.last_modified
            parsed = parse_feed(response.body)
    except FetchError as error:
        status, error_code = "failed", str(error)[:200]
    except Exception as error:  # malformed XML or unexpected parser failure: skip the source this round
        status, error_code = "failed", f"parse: {type(error).__name__}"

    finished = datetime.now(timezone.utc)
    with connection() as database:
        if status in {"ok", "not_modified"}:
            created = store_items(database, source, parsed, finished)
            failures = 0
            delay = timedelta(minutes=source.schedule_minutes)
        else:
            failures = state["consecutive_failures"] + 1
            # Back off instead of hammering a failing source; it retries on its own.
            delay = timedelta(minutes=source.schedule_minutes * 2 ** min(failures, 4))
        database.execute(
            """UPDATE source SET etag = ?, last_modified = ?, last_checked_at = ?, last_status = ?,
               consecutive_failures = ?, next_run_at = ? WHERE id = ?""",
            (etag, modified, iso(finished), status if not error_code else f"{status}: {error_code}",
             failures, iso(finished + delay), source.id),
        )
        database.execute(
            "UPDATE run_record SET finished_at = ?, status = ?, items_new = ?, error_code = ? WHERE id = ?",
            (iso(finished), status, created, error_code, run_id),
        )
    if failures >= 3:
        log.warning("source %s has failed %d times in a row; backing off", source.id, failures)
    return status


def run_due(fetch=guarded_get) -> dict[str, str]:
    """Run every active source whose schedule is due, then rescore stories."""
    sources = load_registry()
    now = datetime.now(timezone.utc)
    with connection() as database:
        sync_sources(database, sources)
        due = due_sources(database, sources, now)
    with connection() as database:
        purge_expired(database, now)
    with connection() as database:
        purge_expired(database, now)
    # Sources on the same host run one after another (rate limit); different hosts run in parallel.
    groups: dict[str, list[Source]] = {}
    for source in due:
        groups.setdefault(urlsplit(source.url).hostname or source.id, []).append(source)
    results: dict[str, str] = {}

    def run_group(group: list[Source]) -> None:
        for source in group:
            results[source.id] = ingest_source(source, fetch=fetch)

    if groups:
        with ThreadPoolExecutor(max_workers=min(len(groups), 6)) as pool:
            list(pool.map(run_group, groups.values()))
    if results:
        with connection() as database:
            rescore(database, datetime.now(timezone.utc))
    return results
