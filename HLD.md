# High-Level Design: AI News Platform

Status: Draft v1.0
Related: PRD.md, LLD.md, DESIGN.md, DATA_SOURCES.md, SECURITY.md

## 1. Purpose

This document describes the system architecture of the AI News Platform at a level that shows its major components, their responsibilities, and how data flows between them. Implementation detail is in LLD.md.

## 2. Architecture overview

The system is organised into seven layers. Data moves top to bottom, from external sources to the user, and security and quality controls apply across the stack.

1. External data layer: RSS feeds, official APIs, approved web extraction, research repositories.
2. News ingestion layer: scheduled job, source fetchers, content parser, data normalisation.
3. AI intelligence layer: duplicate detection, topic classification, credibility assessment, importance scoring, LLM processing, summary generation, impact and opportunity analysis.
4. Data storage layer: relational database, cache, processing and audit logs.
5. Application backend: authentication and access control, REST API, sharing service, settings service.
6. Presentation layer: dashboard, category pages, article details, settings.
7. Security and quality: input validation, SSRF protection, prompt injection protection, monitoring and error handling, automated security and functional tests.

## 3. Context diagram

```
 Sources (RSS, APIs, approved web, research repos)
        |
        v
 Ingestion + AI pipeline (batch, scheduled)
        |
        v
 Storage (PostgreSQL, Redis cache, audit logs)
        |
        v
 REST API  <---->  Auth / Settings / Sharing
        |
        v
 Web app (dashboard, categories, article, settings)
        |
        v
 Reader --> WhatsApp / LinkedIn / Facebook / copy link
```

## 4. Components

### 4.1 Scheduled job
Triggers ingestion for all active sources on a schedule and accepts manual triggers for one source. Writes a run record with start time, end time and result counts.

### 4.2 Source fetchers
One fetcher per source type (RSS, API, web extraction, research repository). Each fetcher enforces the approved source list, applies rate limits, respects robots and terms, and blocks requests to private network addresses (see SECURITY.md).

### 4.3 Content parser and normalisation
Converts raw feeds, JSON payloads and HTML into a common item record. Removes markup, detects language, extracts dates and canonical URLs.

### 4.4 AI intelligence pipeline
Runs as an ordered pipeline on each new item:
1. Duplicate detection (embedding similarity and URL canonicalisation) groups items into stories.
2. Topic classification assigns categories.
3. Credibility assessment scores the source and corroboration.
4. Importance scoring ranks the story.
5. LLM processing generates the summary, impact analysis and opportunity notes.
Each stage writes its output and version to storage, so any stage can be re-run.

### 4.5 Storage
- Relational database (PostgreSQL): sources, items, stories, scores, summaries, users, settings, run records.
- Cache (Redis): dashboard and category responses, hot story lookups.
- Processing and audit logs: append-only records of every automated decision and LLM call.

### 4.6 Application backend
- Authentication and access control: sign-in, sessions, role checks.
- REST API: read endpoints for stories and categories, write endpoints for settings and operator actions.
- Sharing service: builds share links and share-target URLs for each platform.
- Settings service: stores and validates per-user preferences.

### 4.7 Web application
Server-rendered or static-first pages with client enhancements. Four views: dashboard, category pages, article details, settings.

### 4.8 Security and quality
Cross-cutting controls described in SECURITY.md and DESIGN.md. Automated tests run in CI and on a nightly schedule against the staging environment.

## 5. Key flows

### 5.1 Ingestion to publication
1. Scheduled job selects active sources.
2. Fetcher retrieves items, respecting limits and allow-lists.
3. Parser and normaliser produce item records and store them.
4. AI pipeline processes new items into stories.
5. Scores and summaries are written; cache entries are invalidated for affected categories.

### 5.2 Reader views a story
1. Browser requests the dashboard.
2. API returns cached story list, or reads from storage and fills the cache.
3. Reader opens an article; API returns summary, analysis, duplicate sources and share options.

### 5.3 Reader shares a story
1. Reader chooses a platform or copy link.
2. Sharing service returns a link containing only the story identifier.
3. Platform or clipboard receives the link. No personal data leaves the platform.

## 6. Data model (summary)

| Entity | Key fields |
|---|---|
| Source | id, name, type, url, owner, status, last_checked_at |
| Item | id, source_id, title, body_excerpt, url, published_at, language, normalised_at |
| Story | id, canonical_title, first_seen_at, item_count |
| Story score | story_id, credibility, importance, model_version, scored_at |
| Summary | story_id, summary_text, impact_text, model_name, prompt_version, created_at |
| User | id, email, role, created_at |
| Settings | user_id, categories, date_range, density |
| Run record | id, source_id or job, started_at, finished_at, status, counts |

Full schema is in LLD.md.

## 7. Deployment view

- Web app and REST API deployed as stateless containers behind a load balancer with TLS.
- Ingestion workers and AI pipeline run as separate worker containers, scaled by queue depth.
- PostgreSQL and Redis as managed services with backups and point-in-time recovery.
- Separate staging and production environments. No production secrets in staging.

## 8. Cross-cutting concerns

- Observability: structured logs, metrics for fetch success, pipeline latency, LLM cost and errors, dashboards and alerts.
- Configuration: environment variables and a version-controlled source registry.
- Failure handling: retries with backoff for fetches; dead-letter queue for items failing a pipeline stage; circuit breaker for LLM calls.
- Cost control: LLM calls only after deduplication and only for stories above a minimum score.

## 9. Technology choices (proposed)

| Concern | Proposed choice |
|---|---|
| Backend API | Python with FastAPI |
| Workers | Python with a task queue (e.g., Celery or RQ) |
| Database | PostgreSQL |
| Cache | Redis |
| Frontend | TypeScript with a component framework, server-rendered where practical |
| Embeddings | Provider embedding model, stored with pgvector |
| LLM | Provider API behind an internal adapter |
| Hosting | Container platform with managed Postgres and Redis |

These are proposals for review and may change during implementation.

## 10. Risks and open decisions

- Choice of LLM provider and data-processing terms.
- Whether reading requires sign-in (affects caching strategy).
- Refresh frequency versus LLM cost.
