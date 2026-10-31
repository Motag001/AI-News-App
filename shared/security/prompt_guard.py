"""Prompt-injection heuristics and model-output sanitising (SECURITY.md section 5)."""

import html
import re

INJECTION_PATTERNS = re.compile(
    r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier|system)\s+"
    r"(instructions?|prompts?|rules?|messages?)"
    r"|you\s+are\s+now\b|\bnew\s+instructions?\s*:|\bsystem\s+prompt\b|reveal\s+(your|the)\s+(prompt|instructions|key)"
    r"|<\|[a-z_]+\|>|\bjailbreak\b|\bdo\s+anything\s+now\b|<<<|>>>",
    re.I,
)
TAG = re.compile(r"<[^>]*>")
URL = re.compile(r"https?://|www\.", re.I)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SPACE = re.compile(r"\s+")


class UnsafeOutput(ValueError):
    """Model output that must not be published."""


def looks_like_injection(*texts: str | None) -> bool:
    """True if any text contains a known prompt-injection pattern; such stories are kept out of AI input."""
    return any(text and INJECTION_PATTERNS.search(text) for text in texts)


def neutralise_delimiters(text: str) -> str:
    """Remove the delimiter tokens used by our prompts so source text cannot close a block early."""
    return text.replace("<<<", "").replace(">>>", "")


def clean_model_text(value: object, *, max_chars: int, min_chars: int = 1) -> str:
    """Return plain text from model output: no markup, no links, bounded length; else raise UnsafeOutput."""
    if not isinstance(value, str):
        raise UnsafeOutput("Expected text.")
    text = SPACE.sub(" ", CONTROL.sub("", TAG.sub(" ", html.unescape(value)))).strip()
    if URL.search(text):
        raise UnsafeOutput("Links are not allowed in generated text.")
    if "<" in text or ">" in text:
        raise UnsafeOutput("Markup is not allowed in generated text.")
    if not min_chars <= len(text) <= max_chars:
        raise UnsafeOutput("Text length is outside the allowed range.")
    return text
