CREATE TABLE IF NOT EXISTS story (
    id TEXT PRIMARY KEY,
    canonical_title TEXT NOT NULL,
    category TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    impact_text TEXT NOT NULL,
    opportunity_text TEXT NOT NULL,
    credibility REAL NOT NULL CHECK (credibility >= 0 AND credibility <= 1),
    importance REAL NOT NULL CHECK (importance >= 0 AND importance <= 1),
    published_at TEXT NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1))
);

CREATE TABLE IF NOT EXISTS story_source (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 3),
    url TEXT NOT NULL,
    author TEXT,
    published_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_story_category_published
    ON story(category, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_importance
    ON story(importance DESC, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_source_story
    ON story_source(story_id);
