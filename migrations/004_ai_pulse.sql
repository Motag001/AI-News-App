-- AI Pulse: one published edition per calendar date (UTC), its stories and one challenge.
-- Stories are snapshotted into pulse_story so an edition stays complete after the 30-day
-- retention job deletes the underlying story (story_id becomes NULL, nothing else changes).
CREATE TABLE pulse_edition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edition_date TEXT NOT NULL UNIQUE CHECK (edition_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    edition_number INTEGER NOT NULL UNIQUE,
    editorial_introduction TEXT NOT NULL,
    story_count INTEGER NOT NULL CHECK (story_count BETWEEN 1 AND 5),
    estimated_reading_time INTEGER NOT NULL CHECK (estimated_reading_time >= 1),
    generation_status TEXT NOT NULL DEFAULT 'published' CHECK (generation_status IN ('published')),
    mode TEXT NOT NULL CHECK (mode IN ('ai', 'extractive')),
    model_name TEXT,
    prompt_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    selection_json TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE pulse_story (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edition_id INTEGER NOT NULL REFERENCES pulse_edition(id) ON DELETE CASCADE,
    story_id TEXT REFERENCES story(id) ON DELETE SET NULL,
    display_order INTEGER NOT NULL CHECK (display_order BETWEEN 1 AND 5),
    headline TEXT NOT NULL,
    pulse_summary TEXT NOT NULL,
    why_it_matters TEXT,
    category TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    UNIQUE (edition_id, display_order)
);

CREATE TABLE pulse_challenge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edition_id INTEGER NOT NULL UNIQUE REFERENCES pulse_edition(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer_options TEXT NOT NULL,  -- JSON array of 3 or 4 strings
    correct_index INTEGER NOT NULL CHECK (correct_index BETWEEN 0 AND 3),
    correct_answer TEXT NOT NULL,
    explanation TEXT NOT NULL,
    question_type TEXT NOT NULL CHECK (question_type IN ('edition', 'general')),
    created_at TEXT NOT NULL
);

-- Audit and cost record for every generation attempt, successful or not.
CREATE TABLE pulse_generation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edition_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'invalid_output', 'api_error', 'no_candidates')),
    model_name TEXT,
    prompt_version TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0,
    error_code TEXT
);

CREATE INDEX idx_pulse_story_edition ON pulse_story(edition_id, display_order);
CREATE INDEX idx_pulse_story_source_story ON pulse_story(story_id);
CREATE INDEX idx_pulse_log_date ON pulse_generation_log(edition_date, created_at);
