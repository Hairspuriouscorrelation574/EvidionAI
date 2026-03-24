"""
SQLite database layer for the EvidionAI API gateway.

Schema
------
projects  — top-level workspaces that group related chats
chats     — individual research conversations
messages  — user / assistant turns within a chat

The database file lives at ``DATA_DIR/evidionai.db``, which is mounted as a
Docker volume so data persists across container restarts.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "evidionai.db")

# One connection per thread (sqlite3 connections are not thread-safe)
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


@contextmanager
def get_db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    """Create all tables on first startup (idempotent)."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chats (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chats_project ON chats(project_id);

            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id      TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                role         TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content      TEXT NOT NULL DEFAULT '',
                full_history TEXT,
                status       TEXT NOT NULL DEFAULT 'done'
                                 CHECK(status IN ('done', 'pending', 'error')),
                created_at   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
        """)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
