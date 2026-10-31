"""FastAPI application for the AI News Platform prototype."""

import asyncio
import logging
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode, urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.store import connection, initialise_database
from shared.categories import CATEGORIES
from workers.ingest.run import run_due


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
STORY_ID_PATTERN = re.compile(r"^[a-z0-9-]{1,80}$")
parsed_app_url = urlsplit(APP_BASE_URL)
if (
    parsed_app_url.scheme not in {"http", "https"}
    or not parsed_app_url.netloc
    or parsed_app_url.username is not None
    or parsed_app_url.password is not None
    or parsed_app_url.path
    or parsed_app_url.query
    or parsed_app_url.fragment
):
    raise RuntimeError("APP_BASE_URL must be an HTTP(S) origin without a path or credentials.")


log = logging.getLogger("scheduler")


async def ingest_loop() -> None:
    """Check for due sources every minute; each source follows its own schedule_minutes."""
    while True:
        try:
            results = await asyncio.to_thread(run_due)
            if results:
                log.info("ingest run: %s", results)
        except Exception:
            log.exception("ingest run failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialise_database()
    task = None
    if os.getenv("INGEST_ENABLED", "true").lower() != "false":
        task = asyncio.create_task(ingest_loop())
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="AI News Platform",
    version="0.1.0",
    description="A local prototype of a source-linked AI and robotics news reader.",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets"), name="assets")


def problem(status: int, title: str, detail: str | None = None) -> JSONResponse:
    """RFC 7807 problem+json error body (LLD section 3.10)."""
    body = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


@app.exception_handler(StarletteHTTPException)
async def http_problem(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return problem(exc.status_code, HTTPStatus(exc.status_code).phrase, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_problem(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = ", ".join(sorted({".".join(str(p) for p in e["loc"][1:]) or "request" for e in exc.errors()}))
    return problem(422, "Invalid request", f"Check these parameters: {fields}.")


ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("ALLOWED_HOSTS", f"localhost,127.0.0.1,{parsed_app_url.hostname}").split(",")
    if host.strip()
]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)  # blocks Host-header spoofing

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
_recent_requests: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next) -> Response:
    """Per-client sliding-window limit on the JSON API (SECURITY.md section 8)."""
    if request.url.path.startswith("/api/") and request.client:
        now = time.monotonic()
        window = _recent_requests[request.client.host]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= RATE_LIMIT_PER_MINUTE:
            response = problem(429, "Too many requests", "Slow down and try again in a minute.")
            response.headers["Retry-After"] = "60"
            return response
        window.append(now)
        if len(_recent_requests) > 10_000:  # bound memory under a flood of distinct clients
            for key in [k for k, v in _recent_requests.items() if not v or now - v[-1] > 60]:
                del _recent_requests[key]
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' https:; connect-src 'self'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'; object-src 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


class StorySummary(BaseModel):
    id: str
    title: str
    category: str
    summary: str
    credibility: float
    credibility_label: Literal["High", "Medium", "Low"]
    importance: float
    published_at: str
    source_name: str
    source_count: int
    image_url: str | None = None


class StoryList(BaseModel):
    items: list[StorySummary]
    next_cursor: str | None
    total: int


def credibility_label(score: float) -> Literal["High", "Medium", "Low"]:
    if score >= 0.75:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


def require_story_id(story_id: str) -> str:
    if not STORY_ID_PATTERN.fullmatch(story_id):
        raise HTTPException(status_code=404, detail="Story not found.")
    return story_id


def story_link(story_id: str) -> str:
    return f"{APP_BASE_URL}/story/{quote(story_id, safe='')}"


def row_to_summary(row) -> dict:
    return {
        "id": row["id"],
        "title": row["canonical_title"],
        "category": row["category"],
        "summary": row["summary_text"],
        "credibility": row["credibility"],
        "credibility_label": credibility_label(row["credibility"]),
        "importance": row["importance"],
        "published_at": row["published_at"],
        "source_name": row["source_name"],
        "source_count": row["source_count"],
        "image_url": row["image_url"],
    }


@app.get("/api/v1/health")
def health() -> dict:
    with connection() as database:
        sources = database.execute(
            "SELECT COUNT(*) AS total, SUM(last_status LIKE 'ok%' OR last_status = 'not_modified') AS healthy, "
            "MAX(last_checked_at) AS last_checked FROM source"
        ).fetchone()
    return {
        "status": "ok",
        "sources": sources["total"],
        "sources_healthy": sources["healthy"] or 0,
        "last_checked_at": sources["last_checked"],
    }


@app.get("/api/v1/categories")
def categories() -> list[dict[str, int | str]]:
    with connection() as database:
        counts = {
            row["category"]: row["count"]
            for row in database.execute(
                "SELECT category, COUNT(*) AS count FROM story WHERE needs_review = 0 GROUP BY category"
            )
        }
    return [{"name": category, "count": counts.get(category, 0)} for category in CATEGORIES]


@app.get("/api/v1/stories", response_model=StoryList)
def list_stories(
    category: str | None = Query(default=None, max_length=40),
    date_range: Literal["24h", "7d", "30d"] = "7d",
    min_credibility: Literal["all", "medium", "high"] = "all",
    sort: Literal["importance", "recent"] = "importance",
    q: str | None = Query(default=None, max_length=120),
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
) -> StoryList:
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="Unknown category.")

    conditions = ["s.needs_review = 0"]
    parameters: list[object] = []
    if category:
        conditions.append("s.category = ?")
        parameters.append(category)
    if min_credibility == "medium":
        conditions.append("s.credibility >= ?")
        parameters.append(0.5)
    elif min_credibility == "high":
        conditions.append("s.credibility >= ?")
        parameters.append(0.75)
    if q and q.strip():
        conditions.append(
            "(s.canonical_title LIKE ? ESCAPE '!' OR s.summary_text LIKE ? ESCAPE '!')"
        )
        escaped = q.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        search_term = f"%{escaped}%"
        parameters.extend((search_term, search_term))

    with connection() as database:
        parameters.append({"24h": "-1 day", "7d": "-7 days", "30d": "-30 days"}[date_range])
        date_condition = "datetime(s.published_at) >= datetime('now', ?)"
        where = " AND ".join([*conditions, date_condition])
        # `where` and `order` are assembled only from fixed literals above; every user value is a bound parameter.
        total = database.execute(
            f"SELECT COUNT(*) FROM story s WHERE {where}",  # nosec B608
            parameters,
        ).fetchone()[0]
        order = "s.importance DESC, s.published_at DESC" if sort == "importance" else "s.published_at DESC"
        rows = database.execute(
            f"""
            SELECT s.*,
                   COALESCE((SELECT name FROM story_source WHERE story_id = s.id
                             ORDER BY tier, published_at LIMIT 1), 'Unknown source') AS source_name,
                   COUNT(DISTINCT ss.name) AS source_count
            FROM story s
            LEFT JOIN story_source ss ON ss.story_id = s.id
            WHERE {where}
            GROUP BY s.id
            ORDER BY {order}
            LIMIT ? OFFSET ?
            """,  # nosec B608
            [*parameters, limit + 1, cursor],
        ).fetchall()

    has_more = len(rows) > limit
    items = [row_to_summary(row) for row in rows[:limit]]
    next_cursor = str(cursor + limit) if has_more else None
    return StoryList(items=items, next_cursor=next_cursor, total=total)


@app.get("/api/v1/stories/{story_id}")
def get_story(story_id: str) -> dict:
    story_id = require_story_id(story_id)
    with connection() as database:
        story = database.execute(
            "SELECT * FROM story WHERE id = ? AND needs_review = 0",
            (story_id,),
        ).fetchone()
        if story is None:
            raise HTTPException(status_code=404, detail="Story not found.")
        sources = database.execute(
            """
            SELECT name, tier, url, author, published_at, attribution
            FROM story_source WHERE story_id = ?
            ORDER BY tier, name
            """,
            (story_id,),
        ).fetchall()

    summary = {
        "id": story["id"],
        "title": story["canonical_title"],
        "category": story["category"],
        "summary": story["summary_text"],
        "impact": story["impact_text"],
        "opportunity": story["opportunity_text"],
        "credibility": story["credibility"],
        "credibility_label": credibility_label(story["credibility"]),
        "importance": story["importance"],
        "published_at": story["published_at"],
        "image_url": story["image_url"],
        "sources": [dict(source) for source in sources],
        "ai_generated": False,
    }
    return summary


@app.get("/api/v1/stories/{story_id}/share-links")
def share_links(story_id: str) -> dict[str, str]:
    story_id = require_story_id(story_id)
    with connection() as database:
        story = database.execute(
            "SELECT canonical_title FROM story WHERE id = ? AND needs_review = 0",
            (story_id,),
        ).fetchone()
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found.")

    link = story_link(story_id)
    message = f"{story['canonical_title']} {link}"
    return {
        "copy": link,
        "whatsapp": f"https://wa.me/?{urlencode({'text': message})}",
        "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?{urlencode({'url': link})}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?{urlencode({'u': link})}",
    }


@app.get("/", include_in_schema=False)
@app.get("/story/{story_id}", include_in_schema=False)
@app.get("/category/{category}", include_in_schema=False)
@app.get("/settings", include_in_schema=False)
def index(request: Request) -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")
