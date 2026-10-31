"""Deterministic credibility and importance scoring primitives."""

from datetime import datetime, timezone
from math import exp, log

from shared.categories import CATEGORY_WEIGHTS


def credibility_score(
    source_tiers: list[int],
    corroborating_sources: int,
    has_author: bool,
    has_published_date: bool,
) -> float:
    """Score source quality and corroboration without relying on an LLM."""
    if not source_tiers:
        return 0.0
    if any(tier not in (1, 2, 3) for tier in source_tiers):
        raise ValueError("Source tiers must be 1, 2 or 3.")
    if corroborating_sources < 1:
        raise ValueError("Corroborating source count must be at least one.")

    reputation = sum((4 - tier) / 3 for tier in source_tiers) / len(source_tiers)
    corroboration = min(log(corroborating_sources + 1, 2) / 2, 1.0)
    score = 0.5 * reputation + 0.5 * corroboration
    if not has_author:
        score -= 0.05
    if not has_published_date:
        score -= 0.05
    return round(min(max(score, 0.0), 1.0), 4)


def importance_score(
    published_at: datetime,
    reach: float,
    credibility: float,
    category: str,
    now: datetime | None = None,
) -> float:
    """Apply the documented deterministic scoring formula."""
    if category not in CATEGORY_WEIGHTS:
        raise ValueError("Unknown story category.")
    if not 0 <= reach <= 1 or not 0 <= credibility <= 1:
        raise ValueError("Reach and credibility must be between zero and one.")

    current_time = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None or current_time.tzinfo is None:
        raise ValueError("Scoring timestamps must be timezone-aware.")
    age_hours = max((current_time - published_at).total_seconds() / 3600, 0)
    recency = exp(-log(2) * age_hours / 24)
    score = (
        0.35 * recency
        + 0.25 * reach
        + 0.25 * credibility
        + 0.15 * CATEGORY_WEIGHTS[category]
    )
    return round(min(max(score, 0.0), 1.0), 4)
