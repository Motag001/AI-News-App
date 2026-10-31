# Low-Level Design: AI News Platform

Status: Draft v1.0
Related: HLD.md, PRD.md, SECURITY.md, DATA_SOURCES.md

## 1. Scope

This document specifies modules, interfaces, data schema, processing rules and error handling for v1. Names and types are proposals and may change during implementation.

## 2. Repository layout (proposed)

```
ai-news-platform/
  api/                  FastAPI app (routers, schemas, auth)
  workers/
    ingest/             scheduler, fetchers, parser, normaliser
    intelligence/       dedup, classify, credibility, score, llm, summary
  web/                  frontend app (dashboard, category, article, settings)
  shared/
    config/             settings loader, source registry loader
    models/             ORM models and migrations
    security/           url_guard, input validators, prompt_guard
    logging/            structured logger
  sources/
    registry.yaml       approved source list
  tests/
    unit/
    integration/
    security/
  migrations/
  docs/
```

## 3. Modules

### 3.1 Scheduler (`workers/ingest/scheduler.py`)
- `run_scheduled_ingest(now) -> RunSummary`: selects sources where `status = active` and `next_run_at <= now`, enqueues one fetch job per source.
- `run_manual_ingest(source_id) -> RunSummary`: restricted to operator role.
- Writes a `run_record` at start and end.

### 3.2 Fetchers (`workers/ingest/fetchers/`)
Common interface:

```python
class Fetcher(Protocol):
    source_type: str
    def fetch(self, source: Source, since: datetime | None) -> FetchResult: ...
```

Implementations:
- `RssFetcher`: parses feed XML, honours ETag and Last-Modified.
- `ApiFetcher`: calls official APIs with credentials from the secret store, honours rate-limit headers.
- `WebExtractFetcher`: fetches approved pages only, extracts article text with a readability library, respects robots.txt and per-domain rate limits.
- `ResearchRepoFetcher`: queries repository search endpoints (e.g., arXiv) for configured categories.

All fetchers call `shared.security.url_guard.check_url()` before any network request (see SECURITY.md, section 4).

Timeouts: connect 5 s, read 15 s. Max response size 5 MB. Max redirects 3.

### 3.3 Parser and normaliser (`workers/ingest/normalise.py`)
- `normalise(raw: RawItem) -> Item`
- Steps: strip HTML, decode entities, extract plain-text excerpt (max 2,000 characters), canonicalise URL (remove tracking parameters, lowercase host), parse dates to UTC, detect language.
- Writes `item` rows with a unique constraint on `(source_id, canonical_url)`.

### 3.4 Duplicate detection (`workers/intelligence/dedup.py`)
- Step 1: exact match on canonical URL or normalised title hash.
- Step 2: embedding similarity over the last 72 hours; threshold 0.88 (configurable).
- Output: `story_id` assigned to the item; new story created if no match.

### 3.5 Classification (`workers/intelligence/classify.py`)
- Rule-based hints from source metadata first, then LLM classification constrained to a fixed category list.
- Output: `story.category` and `story.category_confidence`.

### 3.6 Credibility assessment (`workers/intelligence/credibility.py`)
- Score = weighted sum of source tier (from the registry), corroboration count (distinct sources in the story), and penalties for missing author or date.
- Output range 0 to 1, mapped to labels: high (≥ 0.75), medium (0.5 to 0.75), low (< 0.5).

### 3.7 Importance scoring (`workers/intelligence/score.py`)
- Score = 0.35 × recency + 0.25 × reach + 0.25 × credibility + 0.15 × category weight.
- Recency decays exponentially with a 24-hour half-life.
- Stored with `scoring_version`.

### 3.8 LLM processing (`workers/intelligence/llm.py`)
- Adapter interface `LlmClient.complete(prompt, schema) -> dict`.
- Only stories with importance ≥ threshold (default 0.4) are sent to the LLM.
- Input is the story's canonical title and excerpts from up to three items, wrapped in delimiters. Instructions are kept in a separate system prompt (see SECURITY.md section 5).
- Output must validate against a JSON schema; invalid output is retried once, then the story is flagged `needs_review`.
- Every call is logged with model, prompt version, token counts and latency.

### 3.9 Summary and analysis (`workers/intelligence/summary.py`)
- Produces `summary_text` (≤ 80 words), `impact_text` (≤ 60 words) and `opportunity_text` (≤ 60 words).
- Writes to `summary` table with `prompt_version` and `model_name`.

### 3.10 API (`api/`)
Endpoints (all JSON, prefix `/api/v1`):

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | /stories | List stories; params: category, from, to, min_credibility, sort, page | Public or user |
| GET | /stories/{id} | Story details with summary, analysis, item sources | Public or user |
| GET | /categories | Category list with counts | Public |
| GET | /me/settings | Read user settings | User |
| PUT | /me/settings | Update user settings | User |
| GET | /stories/{id}/share-links | Share URLs for each platform | Public |
| POST | /auth/sign-in | Start sign-in | None |
| POST | /auth/sign-out | End session | User |
| POST | /ops/ingest/{source_id} | Manual ingest | Operator |
| GET | /ops/health | Health and last run status | Operator |

Pagination: cursor-based, default 20, max 50.
Errors: RFC 7807 problem+json.

### 3.11 Sharing (`api/sharing.py`)
- Builds share URLs:
  - WhatsApp: `https://wa.me/?text=<encoded title + story link>`
  - LinkedIn: share-offsite URL with the story link.
  - Facebook: sharer URL with the story link.
  - Copy: the story link only.
- Story link format: `https://<app-host>/story/{story_id}`. No user identifiers.

### 3.12 Settings (`api/settings.py`)
- Validates categories against the category list, date range against allowed values, density against enum.
- Stores in `user_settings`.

## 4. Data schema

```sql
CREATE TABLE source (
  id            UUID PRIMARY KEY,
  name          TEXT NOT NULL,
  type          TEXT NOT NULL CHECK (type IN ('rss','api','web','research')),
  url           TEXT NOT NULL,
  owner         TEXT NOT NULL,
  tier          SMALLINT NOT NULL CHECK (tier BETWEEN 1 AND 3),
  status        TEXT NOT NULL CHECK (status IN ('active','paused','disabled')),
  schedule_minutes INT NOT NULL DEFAULT 60,
  next_run_at   TIMESTAMPTZ,
  last_checked_at TIMESTAMPTZ,
  last_status   TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE item (
  id            UUID PRIMARY KEY,
  source_id     UUID NOT NULL REFERENCES source(id),
  story_id      UUID REFERENCES story(id),
  title         TEXT NOT NULL,
  author        TEXT,
  canonical_url TEXT NOT NULL,
  excerpt       TEXT,
  language      TEXT,
  published_at  TIMESTAMPTZ,
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  title_hash    BYTEA NOT NULL,
  UNIQUE (source_id, canonical_url)
);

CREATE TABLE story (
  id              UUID PRIMARY KEY,
  canonical_title TEXT NOT NULL,
  category        TEXT,
  category_confidence REAL,
  first_seen_at   TIMESTAMPTZ NOT NULL,
  item_count      INT NOT NULL DEFAULT 1,
  needs_review    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE story_score (
  story_id      UUID REFERENCES story(id),
  credibility   REAL NOT NULL,
  importance    REAL NOT NULL,
  scoring_version TEXT NOT NULL,
  scored_at     TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (story_id, scoring_version)
);

CREATE TABLE summary (
  id              UUID PRIMARY KEY,
  story_id        UUID NOT NULL REFERENCES story(id),
  summary_text    TEXT NOT NULL,
  impact_text     TEXT NOT NULL,
  opportunity_text TEXT NOT NULL,
  model_name      TEXT NOT NULL,
  prompt_version  TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
  id          UUID PRIMARY KEY,
  email       TEXT UNIQUE NOT NULL,
  role        TEXT NOT NULL CHECK (role IN ('reader','operator')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_settings (
  user_id     UUID PRIMARY KEY REFERENCES app_user(id),
  categories  TEXT[] NOT NULL DEFAULT '{}',
  date_range  TEXT NOT NULL DEFAULT '7d',
  density     TEXT NOT NULL DEFAULT 'comfortable'
);

CREATE TABLE run_record (
  id          UUID PRIMARY KEY,
  job_type    TEXT NOT NULL,
  source_id   UUID REFERENCES source(id),
  started_at  TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  status      TEXT NOT NULL,
  items_new   INT DEFAULT 0,
  error_code  TEXT
);

CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  target_id   TEXT,
  detail      JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Indexes: `item(published_at)`, `story(category, first_seen_at)`, `story_score(importance DESC)`, pgvector HNSW index on item embeddings (stored in `item_embedding`).

## 5. Caching

- Keys: `stories:{category}:{range}:{cursor}`, `story:{id}`, `categories`.
- TTL: 5 minutes for lists, 1 hour for story detail.
- Invalidation: when the pipeline writes a story, delete affected category keys.
- Personalised settings are never cached in shared keys.

## 6. Error handling and retries

| Stage | Failure | Behaviour |
|---|---|---|
| Fetch | Timeout or 5xx | Retry 3 times, exponential backoff, then mark run failed |
| Fetch | 4xx or parse error | Record error, skip item, continue |
| Normalise | Invalid date | Use fetched_at, flag low credibility |
| Dedup | Embedding service down | Use title-hash match only, queue for later re-check |
| LLM | Timeout or rate limit | Retry with backoff; circuit opens after 5 failures in 5 minutes |
| LLM | Invalid JSON | Retry once, then `needs_review` |
| Any stage | Unhandled exception | Send item to dead-letter queue with stage name |

## 7. Configuration

Environment variables:
- `DATABASE_URL`, `REDIS_URL`
- `LLM_PROVIDER`, `LLM_MODEL`, `LLM_DAILY_BUDGET_USD`
- `EMBEDDING_MODEL`
- `DEDUP_THRESHOLD` (default 0.88)
- `IMPORTANCE_LLM_THRESHOLD` (default 0.4)
- `INGEST_DEFAULT_INTERVAL_MIN` (default 60)
- `APP_BASE_URL`
- `SESSION_SECRET` (from secret store, never in repo)

Secrets come from the platform secret store. Nothing secret is committed to the repository.

## 8. Observability

- Log fields: `request_id`, `job_id`, `source_id`, `story_id`, `stage`, `duration_ms`, `status`.
- Metrics: `ingest_items_total`, `ingest_failures_total`, `pipeline_stage_seconds`, `llm_tokens_total`, `llm_cost_usd_total`, `api_latency_seconds`.
- Alerts: source failure rate above 20% for 1 hour; LLM budget at 80%; dead-letter queue growing.

## 9. Testing

- Unit tests for normaliser, URL canonicalisation, credibility and scoring functions (pure functions, table-driven).
- Integration tests for each fetcher against recorded fixtures.
- Contract tests for the LLM adapter using a stub client.
- Security tests (see SECURITY.md section 9) run in CI.
- End-to-end tests for the four reading views and the share flow.

## 10. Open items

- Choice of embedding model and vector index parameters.
- Whether story merging can be reversed by operators.
- Retention period for raw item bodies (proposed: 90 days, excerpts kept longer).
