"""SQLite persistence layer for AirNode (Phase 6.6).

Stores watch state, recent files, and small cache rows in a single
SQLite database so they survive restarts without scattered JSON files.

On first run, any existing legacy JSON files are migrated into the DB:
  - `.airnode_watch_state.json` → `watch_state` table
  - `.airnode_recent.json` → `recent_files` table
"""

import json
import sqlite3
import threading
import time
from pathlib import Path

from logging_config import get_logger
from paths import get_data_dir


logger = get_logger(__name__)

_DB_PATH: Path | None = None
_db_lock = threading.Lock()


def _get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = get_data_dir() / "airnode.db"
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    """Open a connection with row access and WAL mode."""
    conn = sqlite3.connect(str(_get_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.Error:
        pass
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS watch_state (
    path TEXT PRIMARY KEY,
    current_time REAL NOT NULL DEFAULT 0,
    duration REAL NOT NULL DEFAULT 0,
    percent REAL NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS recent_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'file',
    opened_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kv_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at REAL
);
"""


def init_db() -> None:
    """Create tables and migrate legacy JSON state files."""
    try:
        with _db_lock, get_connection() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()
        _migrate_legacy_watch_state()
        _migrate_legacy_recent()
        logger.info("SQLite database ready at %s", _get_db_path())
    except Exception:
        logger.exception("Failed to initialise SQLite database")


# ==============================================================================
# Legacy JSON → SQLite migration
# ==============================================================================

def _migrate_legacy_watch_state() -> None:
    """Import `.airnode_watch_state.json` into the watch_state table once."""
    legacy = get_data_dir() / ".airnode_watch_state.json"
    if not legacy.exists():
        return
    try:
        with legacy.open("r", encoding="utf-8") as f:
            data = json.load(f)
        with _db_lock, get_connection() as conn:
            for path, ws in data.items():
                if not isinstance(ws, dict):
                    continue
                conn.execute(
                    """INSERT OR REPLACE INTO watch_state
                       (path, current_time, duration, percent, completed, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        path,
                        float(ws.get("currentTime", 0)),
                        float(ws.get("duration", 0)),
                        float(ws.get("percent", 0)),
                        1 if ws.get("completed") else 0,
                        float(ws.get("updatedAt", time.time())),
                    ),
                )
            conn.commit()
        # Rename the legacy file so it isn't re-imported
        legacy.rename(legacy.with_suffix(".json.migrated"))
        logger.info("Migrated legacy watch state into SQLite")
    except Exception:
        logger.exception("Failed to migrate legacy watch state")


def _migrate_legacy_recent() -> None:
    """Import `.airnode_recent.json` into the recent_files table once."""
    legacy = get_data_dir() / ".airnode_recent.json"
    if not legacy.exists():
        return
    try:
        with legacy.open("r", encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else data.get("recent", [])
        with _db_lock, get_connection() as conn:
            for item in items:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if not path:
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO recent_files (path, name, kind, opened_at)
                       VALUES (?, ?, ?, ?)""",
                    (
                        path,
                        item.get("name", Path(path).name),
                        item.get("kind", "file"),
                        float(item.get("opened_at", item.get("openedAt", time.time()))),
                    ),
                )
            conn.commit()
        legacy.rename(legacy.with_suffix(".json.migrated"))
        logger.info("Migrated legacy recent files into SQLite")
    except Exception:
        logger.exception("Failed to migrate legacy recent files")


# ==============================================================================
# watch_state
# ==============================================================================

def load_watch_state() -> dict:
    """Return the full watch-state map keyed by path (legacy dict shape)."""
    try:
        with _db_lock, get_connection() as conn:
            rows = conn.execute("SELECT * FROM watch_state").fetchall()
        return {
            row["path"]: {
                "currentTime": row["current_time"],
                "duration": row["duration"],
                "percent": row["percent"],
                "completed": bool(row["completed"]),
                "updatedAt": row["updated_at"],
            }
            for row in rows
        }
    except Exception:
        logger.exception("Failed to load watch state from SQLite")
        return {}


def save_watch_state_entry(path: str, current_time: float, duration: float, percent: float, completed: bool) -> None:
    """Upsert a single watch-state entry."""
    try:
        with _db_lock, get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO watch_state
                   (path, current_time, duration, percent, completed, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (path, current_time, duration, percent, 1 if completed else 0, time.time()),
            )
            conn.commit()
    except Exception:
        logger.exception("Failed to save watch state entry")


def clear_watch_state() -> None:
    """Delete all watch-state rows."""
    try:
        with _db_lock, get_connection() as conn:
            conn.execute("DELETE FROM watch_state")
            conn.commit()
    except Exception:
        logger.exception("Failed to clear watch state")


# ==============================================================================
# recent_files
# ==============================================================================

def add_recent_file(path: str, name: str, kind: str = "file") -> None:
    """Record a recently opened file/folder (upsert, bump opened_at)."""
    try:
        with _db_lock, get_connection() as conn:
            conn.execute(
                """INSERT INTO recent_files (path, name, kind, opened_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(path) DO UPDATE SET
                       name = excluded.name,
                       kind = excluded.kind,
                       opened_at = excluded.opened_at""",
                (path, name, kind, time.time()),
            )
            conn.commit()
    except Exception:
        logger.exception("Failed to record recent file")


def get_recent_files(limit: int = 50, kind: str | None = None) -> list[dict]:
    """Return the most-recently opened items, newest first."""
    try:
        sql = "SELECT * FROM recent_files"
        params: list = []
        if kind:
            sql += " WHERE kind = ?"
            params.append(kind)
        sql += " ORDER BY opened_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with _db_lock, get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "path": row["path"],
                "name": row["name"],
                "kind": row["kind"],
                "openedAt": row["opened_at"],
            }
            for row in rows
        ]
    except Exception:
        logger.exception("Failed to load recent files")
        return []


def clear_recent_files() -> None:
    """Delete all recent-file rows."""
    try:
        with _db_lock, get_connection() as conn:
            conn.execute("DELETE FROM recent_files")
            conn.commit()
    except Exception:
        logger.exception("Failed to clear recent files")


# ==============================================================================
# kv_cache
# ==============================================================================

def kv_get(key: str) -> str | None:
    """Return a cached string value if present and unexpired."""
    try:
        with _db_lock, get_connection() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM kv_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        expires = row["expires_at"]
        if expires is not None and expires < time.time():
            return None
        return row["value"]
    except Exception:
        return None


def kv_set(key: str, value: str, ttl_seconds: float | None = None) -> None:
    """Store a string in the cache with an optional TTL."""
    expires = time.time() + ttl_seconds if ttl_seconds else None
    try:
        with _db_lock, get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO kv_cache (key, value, expires_at)
                   VALUES (?, ?, ?)""",
                (key, value, expires),
            )
            conn.commit()
    except Exception:
        logger.exception("Failed to write kv_cache entry")


def kv_delete(key: str) -> None:
    try:
        with _db_lock, get_connection() as conn:
            conn.execute("DELETE FROM kv_cache WHERE key = ?", (key,))
            conn.commit()
    except Exception:
        pass