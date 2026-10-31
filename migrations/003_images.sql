-- Feed-provided image URLs (hot-linked, never downloaded). Reset validators so images are backfilled.
ALTER TABLE item ADD COLUMN image_url TEXT;
ALTER TABLE story ADD COLUMN image_url TEXT;
UPDATE source SET etag = NULL, last_modified = NULL, next_run_at = NULL;
