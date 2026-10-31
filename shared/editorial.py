"""Editorial rules shared by feed ranking and the AI Pulse selection."""

import re

LOW_VALUE = re.compile(
    r"\b(costumes?|halloween|black friday|cyber monday|gift guides?|deals?|coupons?|giveaways?|horoscopes?|quiz|"
    r"podcast|newsletter|video friday|week in review|weekly roundup|roundup|best [\w\s-]{0,30}(to buy|of 20\d\d)|"
    r"how to [\w\s-]{0,20}(your|a)\b)",
    re.I,
)


def is_low_value(title: str) -> bool:
    """Lifestyle, listicle and roundup items that should not lead a news ranking."""
    return bool(LOW_VALUE.search(title))
