# AI News Platform

A responsive prototype for following AI, robotics and technology stories. The current build includes a FastAPI JSON API, a SQLite store, a browser-based dashboard and story pages, category/date/credibility filters, share links, browser-local display preferences, and deterministic scoring helpers.

> **Live data:** the app fetches real stories on its own, in the background, from the approved feeds in `sources/registry.yaml` (arXiv cs.AI and cs.RO, OpenAI, Google DeepMind, Google AI Blog, MIT Technology Review, IEEE Spectrum Robotics, TechCrunch AI). Only titles, short excerpts, links and the feed's own image URL are stored; images are hot-linked from the publisher (https only, no referrer sent) and never downloaded. Stories without a feed image get a coloured category placeholder. The news feed itself uses no LLM (its text is the source's own excerpt); only the optional AI Pulse briefing calls OpenAI, and only if you set a key.

## Run locally (Windows PowerShell)

Prerequisites: Python 3.11 or newer. Node.js, Docker, PostgreSQL and Redis are not required for this prototype.

Run these commands from the project root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload
```

Open `http://localhost:8000`. The app creates `datai_news.db` on first start and fetches every source within about a minute (the first run waits 10 s between requests to the same domain, so arXiv takes a little longer). After that each source refreshes on its own schedule (60–180 minutes) with no input from you. Keep the Uvicorn terminal open; `Ctrl+C` stops it. Set `INGEST_ENABLED=false` in `.env` to stop fetching.

To run the tests, open a second PowerShell window at the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

If PowerShell says the virtual-environment Python executable is missing, create the environment first. If `py -3.11` is unavailable, install Python 3.11+ and use that installed version to create `.venv`.

## How it works

- **Nothing to enter.** Sources are fetched automatically; a failing source backs off and retries by itself, and one outage never removes stored stories.
- **Safety:** every request goes through the SSRF guard (`shared/security/url_guard.py`): https registry URLs only, public IPs only, connection pinned to the checked IP, 3 redirects, 5 MB, 5 s/15 s timeouts. XML is parsed with `defusedxml`.
- **Dedup:** same URL or title, or title-token similarity of 0.6 or more against stories from the last 72 hours, groups items into one story ("also reported by N sources"). Embeddings are not used.
- **Category:** keyword rules plus an optional per-source hint.
- **Credibility (0–1):** source tier plus corroboration across distinct sources, reduced for missing author/date. High ≥ 0.75, Medium ≥ 0.50.
- **Importance (0–1):** `0.35 × recency + 0.25 × reach + 0.25 × credibility + 0.15 × category weight`, 24-hour half-life. Feeds expose no reach data, so reach is a neutral 0.5.
- **Retention:** stories (and their stored items) older than 30 days are deleted automatically on every scheduler pass (every minute and at startup). Change it with `RETENTION_DAYS` in `.env`.
- **Adding a source:** use the `add-news-source` skill, then set `status: active`. Run `python -m shared.config.validate_registry` equivalent: `python -m shared.config.registry`.

## AI Pulse (daily briefing)

"5 stories. 2 minutes. Stay ahead." One edition per UTC calendar day, built from the stories the ingestion pipeline has already collected and scored. Nothing new is fetched for it.

- **Where:** a preview card on the homepage and the full briefing at `/pulse` (archive at `/pulse/YYYY-MM-DD`).
- **Selection** (`workers/intelligence/pulse.py`): stories from the last 72 hours that are not held for review, with credibility ≥ 0.5 and importance ≥ 0.4, ranked by importance. Near-duplicate titles are skipped, at most two stories per category are taken first, stories already featured are never repeated, and stories whose text looks like prompt injection are excluded. If fewer than five qualify, fewer are shown.
- **Writing:** one OpenAI call per edition (at most one retry for an unusable reply) writes the introduction, headline, 50–80 word summary and "why it matters" for each story, and one multiple-choice challenge. The reply is validated strictly (exact story ids and order, word limits, no markup or links, 3–4 unique options, valid answer index). Invalid replies are never published.
- **Without an OpenAI key** the edition is still published, clearly labelled "Automated edition": headlines and summaries come straight from the sources, there is no "why it matters", and the challenge is a general AI-knowledge question from a fixed list, marked as such. If a key is set and OpenAI fails, nothing is invented: the previous edition stays visible with a status message.
- **Cost control:** stored once per day and never regenerated on page views; at most 5 stories, 600 excerpt characters each and 900 output tokens; 3 failed attempts per day with a 15-minute back-off; every attempt (tokens, estimated cost, error code) is logged in `pulse_generation_log`. Each edition records its model, prompt version, input hash and the selection scores so it can be audited.
- **Editorial refresh:** `POST /api/v1/pulse/refresh` with `Authorization: Bearer <PULSE_ADMIN_TOKEN>` regenerates today's edition (the old one is kept if generation fails). It is disabled (404) unless the token is set. Public visitors cannot trigger generation beyond the single capped, once-per-day build.
- **Challenge:** the page never receives the correct answer; `POST /api/v1/pulse/{date}/challenge/answer` checks the choice and returns the result and explanation. The first answer on a device is kept and cannot be changed.
- **Reading streak:** stored only in the browser's `localStorage` (key `aiPulse.v1`), using the visitor's local date. A day counts when the reader reaches the end of the latest briefing or answers its challenge, once per day. No account and no server-side visitor data. **Streaks are specific to one browser on one device and are lost if browser data is cleared.**
- **Edition date** is the UTC date, so for readers far from UTC the edition changes at a different local time.

Endpoints: `GET /api/v1/pulse/today`, `GET /api/v1/pulse/history?limit=`, `GET /api/v1/pulse/{date}`, `POST /api/v1/pulse/{date}/challenge/answer`, `POST /api/v1/pulse/refresh` (operator).

Environment variables (all optional; see `.env.example`): `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`), `PULSE_MAX_OUTPUT_TOKENS`, `PULSE_DAILY_ATTEMPT_LIMIT`, `PULSE_GENERATE_ON_REQUEST`, `PULSE_ADMIN_TOKEN`, `PULSE_ALLOW_EXTRACTIVE`, `PULSE_PRICE_INPUT_PER_M` / `PULSE_PRICE_OUTPUT_PER_M` (for the cost estimate). Set the key only in a local `.env` or your host's secret store.

Tests: `python -m unittest discover -s tests -v` also runs the streak tests with Node.js (`node --test tests/js/streak.test.js`).

## API examples

With the server running, use these URLs in a browser or request them from PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod "http://localhost:8000/api/v1/stories?category=Robotics&date_range=7d"
Invoke-RestMethod http://localhost:8000/api/v1/categories
```

Available read endpoints are `GET /api/v1/health`, `/api/v1/categories`, `/api/v1/stories`, `/api/v1/stories/{id}`, and `/api/v1/stories/{id}/share-links`. Reading is public in this prototype. Share URLs contain only the story identifier.

## Project layout

```text
api/                         FastAPI routes and SQLite persistence
migrations/                  SQLite schema
shared/                      Shared category definitions
sources/registry.yaml        Empty approved-source registry
web/                         Accessible frontend and static assets
workers/ingest/              Ingestion extension point (disabled)
workers/intelligence/        Deterministic scoring and classification helpers
tests/unit/                  API and domain logic tests
.claude/skills/              Source, pipeline and security workflows
```

## Current scope and next steps

Implemented: scheduled ingestion from 8 approved feeds, normalisation, duplicate grouping, classification, scoring, dashboard, category pages, search and filters, story pages with source links and attribution, sharing, browser-local settings, `/api/v1/health` with source status, security headers, and tests.

Not implemented: LLM summaries for the news feed itself, embeddings, sign-in and server-side settings, operator controls, PostgreSQL/Redis, deployment. Follow [PRD.md](PRD.md), [HLD.md](HLD.md), [LLD.md](LLD.md), [DESIGN.md](DESIGN.md), [DATA_SOURCES.md](DATA_SOURCES.md) and [SECURITY.md](SECURITY.md) when extending.
