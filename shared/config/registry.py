"""Load and validate the approved source registry (DATA_SOURCES.md section 4)."""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from shared.categories import CATEGORIES

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "sources" / "registry.yaml"
ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
REQUIRED = (
    "id", "name", "type", "url", "owner", "tier", "status", "schedule_minutes",
    "rate_limit_per_minute", "allowed_paths", "terms_checked_on", "terms_reference",
    "copyright_position", "contact",
)


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    type: str
    url: str
    owner: str
    tier: int
    status: str
    schedule_minutes: int
    rate_limit_per_minute: int
    attribution: str | None = None
    category_hint: str | None = None


def validate(entries: object) -> list[Source]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise RegistryError("Registry must be a list of sources.")
    sources: list[Source] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RegistryError("Each registry entry must be a mapping.")
        missing = [key for key in REQUIRED if entry.get(key) in (None, "") and key != "allowed_paths"]
        if missing or "allowed_paths" not in entry:
            raise RegistryError(f"Source {entry.get('id', '?')} is missing: {', '.join(missing) or 'allowed_paths'}.")
        if not ID_PATTERN.fullmatch(str(entry["id"])) or entry["id"] in seen:
            raise RegistryError(f"Source id {entry['id']!r} is invalid or duplicated.")
        seen.add(entry["id"])
        if entry["type"] not in {"rss", "api", "web", "research"}:
            raise RegistryError(f"Source {entry['id']}: unknown type.")
        if entry["status"] not in {"active", "paused", "disabled"}:
            raise RegistryError(f"Source {entry['id']}: unknown status.")
        if entry["tier"] not in (1, 2, 3):
            raise RegistryError(f"Source {entry['id']}: tier must be 1, 2 or 3.")
        if entry["copyright_position"] != "excerpts_and_links":
            raise RegistryError(f"Source {entry['id']}: only excerpts_and_links is allowed.")
        if entry["type"] == "web" and not entry["allowed_paths"]:
            raise RegistryError(f"Source {entry['id']}: web sources need allowed_paths.")
        if urlsplit(str(entry["url"])).scheme != "https":
            raise RegistryError(f"Source {entry['id']}: url must be https.")
        hint = entry.get("category_hint")
        if hint is not None and hint not in CATEGORIES:
            raise RegistryError(f"Source {entry['id']}: unknown category_hint.")
        minutes = int(entry["schedule_minutes"])
        if minutes < 15:
            raise RegistryError(f"Source {entry['id']}: schedule_minutes must be at least 15.")
        sources.append(Source(
            id=entry["id"], name=str(entry["name"]), type=entry["type"], url=entry["url"],
            owner=str(entry["owner"]), tier=entry["tier"], status=entry["status"],
            schedule_minutes=minutes, rate_limit_per_minute=int(entry["rate_limit_per_minute"]),
            attribution=entry.get("attribution"), category_hint=hint,
        ))
    return sources


def load_registry(path: Path = REGISTRY_PATH) -> list[Source]:
    return validate(yaml.safe_load(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    import sys
    loaded = load_registry(Path(sys.argv[1]) if len(sys.argv) > 1 else REGISTRY_PATH)
    print(f"{len(loaded)} sources valid ({sum(s.status == 'active' for s in loaded)} active).")
