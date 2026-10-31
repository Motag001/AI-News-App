"""Duplicate detection (LLD section 3.4): exact URL/title hash, then title-token similarity.

Embeddings are not configured, so step 2 uses Jaccard similarity of title tokens
over the last 72 hours instead of vector similarity.
"""

import re

from workers.ingest.normalise import normalise_title

THRESHOLD = 0.6
STOPWORDS = frozenset("a an and the of to in on for with is are at by from as its it new how why what".split())


def tokens(title: str) -> frozenset[str]:
    return frozenset(
        word for word in re.split(r"\s+", normalise_title(title)) if word and word not in STOPWORDS
    )


def similarity(first: frozenset[str], second: frozenset[str]) -> float:
    if len(first) < 3 or len(second) < 3:
        return 0.0
    return len(first & second) / len(first | second)


def find_story(database, canonical_url: str, title_hash: str, title: str, since_iso: str) -> str | None:
    row = database.execute(
        "SELECT story_id FROM item WHERE canonical_url = ? OR title_hash = ? LIMIT 1",
        (canonical_url, title_hash),
    ).fetchone()
    if row:
        return row["story_id"]
    wanted = tokens(title)
    best_id, best_score = None, 0.0
    for story in database.execute(
        "SELECT id, canonical_title FROM story WHERE first_seen_at >= ?", (since_iso,)
    ):
        score = similarity(wanted, tokens(story["canonical_title"]))
        if score > best_score:
            best_id, best_score = story["id"], score
    return best_id if best_score >= THRESHOLD else None
