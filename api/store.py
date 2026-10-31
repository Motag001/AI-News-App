"""SQLite persistence and versioned migrations."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATIONS_DIR = ROOT / "migrations"


def database_path() -> Path:
    return Path(os.getenv("DATABASE_PATH", str(ROOT / "data" / "ai_news.db")))


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """Open a short-lived SQLite connection with foreign keys enabled."""
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path, timeout=15)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    database.execute("PRAGMA journal_mode = WAL")
    try:
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def initialise_database() -> None:
    """Apply any migrations that have not run yet, in filename order."""
    with connection() as database:
        database.execute("CREATE TABLE IF NOT EXISTS schema_version (name TEXT PRIMARY KEY)")
        applied = {row[0] for row in database.execute("SELECT name FROM schema_version")}
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration.name in applied:
                continue
            database.executescript(migration.read_text(encoding="utf-8"))
            database.execute("INSERT INTO schema_version (name) VALUES (?)", (migration.name,))
