-- Replaces the fictional demo schema with the live-ingestion schema.
-- Every row in the old tables was fictional sample data, so nothing real is lost.
DROP TABLE IF EXISTS story_source;
DROP TABLE IF EXISTS story;

CREATE TABLE source (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('rss', 'api', 'web', 'research')),
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 3),
    url TEXT NOT NULL,
    attribution TEXT,
    etag TEXT,
    last_modified TEXT,
    next_run_at TEXT,
    last_checked_at TEXT,
    last_status TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE story (
    id TEXT PRIMARY KEY,
    canonical_title TEXT NOT NULL,
    category TEXT NOT NULL,
    category_confidence REAL NOT NULL DEFAULT 0,
    summary_text TEXT NOT NULL DEFAULT '',
    impact_text TEXT,
    opportunity_text TEXT,
    credibility REAL NOT NULL CHECK (credibility >= 0 AND credibility <= 1),
    importance REAL NOT NULL CHECK (importance >= 0 AND importance <= 1),
    scoring_version TEXT NOT NULL DEFAULT 'v1',
    published_at TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1))
);

CREATE TABLE item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES source(id),
    story_id TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    author TEXT,
    canonical_url TEXT NOT NULL,
    excerpt TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    title_hash TEXT NOT NULL,
    UNIQUE (source_id, canonical_url)
);

-- Read model used by the API: one row per source item of a story.
CREATE VIEW story_source AS
SELECT i.story_id AS story_id,
       s.name AS name,
       s.tier AS tier,
       i.canonical_url AS url,
       i.author AS author,
       COALESCE(i.published_at, i.fetched_at) AS published_at,
       s.attribution AS attribution
FROM item i JOIN source s ON s.id = i.source_id;

CREATE TABLE run_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT REFERENCES source(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    items_new INTEGER NOT NULL DEFAULT 0,
    error_code TEXT
);

CREATE INDEX idx_story_category_published ON story(category, published_at DESC);
CREATE INDEX idx_story_importance ON story(importance DESC, published_at DESC);
CREATE INDEX idx_item_story ON item(story_id);
CREATE INDEX idx_item_title_hash ON item(title_hash);
