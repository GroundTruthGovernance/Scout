"""SQLite project database connection + schema management.

Deliberately plain sqlite3 rather than an ORM — see docs/ARCHITECTURE.md
("Tech stack") for why. One Scout project = one .scout.db file.
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from scout._version import SCHEMA_VERSION

_SCHEMA_KEY = "schema_version"


def _schema_sql() -> str:
    return resources.files("scout.core").joinpath("schema.sql").read_text(encoding="utf-8")


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) a Scout project database.

    Applies the schema if the database is new or blank, and returns a
    connection with foreign keys enabled and row access by column name.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Idempotently ensure the schema exists and matches SCHEMA_VERSION.

    All CREATE TABLE statements in schema.sql use IF NOT EXISTS, so this
    is safe to call on every open. If an existing database reports an
    older schema_version, a migration step should run here in future —
    for now (schema_version 3, pre-1.0) we just stamp the version.
    """
    conn.executescript(_schema_sql())

    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key = ?", (_SCHEMA_KEY,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES (?, ?)",
            (_SCHEMA_KEY, SCHEMA_VERSION),
        )
        conn.commit()
    elif row["value"] != SCHEMA_VERSION:
        # No migrations exist yet (pre-1.0 schema). Once the schema is
        # stable across releases, add versioned migration scripts here
        # instead of silently re-stamping.
        conn.execute(
            "UPDATE schema_meta SET value = ? WHERE key = ?",
            (SCHEMA_VERSION, _SCHEMA_KEY),
        )
        conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key = ?", (_SCHEMA_KEY,)
    ).fetchone()
    return row["value"] if row else None
