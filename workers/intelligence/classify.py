"""Deterministic keyword classification into the fixed category list (LLD section 3.5)."""

import re

from shared.categories import CATEGORIES

KEYWORDS = {
    "Robotics": r"\b(robot\w*|humanoid\w*|drone\w*|manipulat\w+|quadruped\w*|exoskeleton\w*|autonomous (vehicle|driving)\w*|self-driving|warehouse automation)\b",
    "Policy": r"\b(regulat\w+|legislat\w+|\blaw\w*|senate|congress|parliament|eu ai act|government|policy|policies|lawsuit|sues?|copyright|antitrust|ban(s|ned)?|export controls?|safety institute|governance)\b",
    "Research": r"\b(paper|preprint|arxiv|study|studies|researchers?|benchmark\w*|we propose|we present|dataset|theorem|ablation)\b",
    "AI models": r"\b(model\w*|gpt[\w-]*|gemini|claude|llama|llm\w*|chatbot\w*|diffusion|transformer\w*|multimodal|fine-tun\w+|reasoning|agents?)\b",
}
HINT_BONUS = 2


def validate_category(category: str | None) -> str | None:
    """Return a known category or ``None`` for an unsupported hint."""
    if category is None:
        return None
    return category if category in CATEGORIES else None


def classify(title: str, excerpt: str, hint: str | None = None) -> tuple[str, float]:
    """Pick a category from title (weighted) and excerpt text; fall back to Industry."""
    scores = {name: 0 for name in KEYWORDS}
    for name, pattern in KEYWORDS.items():
        scores[name] += 2 * len(re.findall(pattern, title, re.I))
        scores[name] += len(re.findall(pattern, excerpt[:600], re.I))
    hint = validate_category(hint)
    if hint in scores:
        scores[hint] += HINT_BONUS
    total = sum(scores.values())
    if total == 0:
        return "Industry", 0.0
    # Ties resolve in KEYWORDS order, which lists the more specific categories first.
    best = max(scores, key=scores.get)
    return best, round(scores[best] / total, 2)
