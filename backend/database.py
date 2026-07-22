"""
Simple SQLite database for PARENTS only.

Important:
- We save chats so parents can review them on the digital twin.
- We do NOT send this history back to the AI (saves API credits/tokens).

Tables:
  chats  -> every child <-> robot exchange (grouped by session_id)
  alerts -> safety / sensitive-topic notifications for parents
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.config import DATABASE_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    """Add a column if an older database file is missing it."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names = {row["name"] for row in rows}
    if column not in names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def init_db() -> None:
    """Create tables if they do not exist yet."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                child_message TEXT NOT NULL,
                ai_reply TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'free',
                session_id TEXT,
                is_flagged INTEGER NOT NULL DEFAULT 0,
                alert_category TEXT,
                alert_severity TEXT,
                alert_summary TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                child_message TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                summary TEXT NOT NULL,
                parent_advice TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                chat_id INTEGER
            )
            """
        )

        _ensure_column(conn, "chats", "session_id", "TEXT")
        _ensure_column(conn, "chats", "is_flagged", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "chats", "alert_category", "TEXT")
        _ensure_column(conn, "chats", "alert_severity", "TEXT")
        _ensure_column(conn, "chats", "alert_summary", "TEXT")
        _ensure_column(conn, "alerts", "chat_id", "INTEGER")
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_chat(
    child_message: str,
    ai_reply: str,
    mode: str = "free",
    session_id: Optional[str] = None,
    is_flagged: bool = False,
    alert_category: Optional[str] = None,
    alert_severity: Optional[str] = None,
    alert_summary: Optional[str] = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO chats
            (created_at, child_message, ai_reply, mode, session_id, is_flagged,
             alert_category, alert_severity, alert_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                child_message,
                ai_reply,
                mode,
                session_id,
                1 if is_flagged else 0,
                alert_category,
                alert_severity,
                alert_summary,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_chat(chat_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    return dict(row) if row else None


def get_recent_chats(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM chats ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_session_chats(session_id: str) -> list[dict]:
    """All messages in one conversation, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM chats WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_conversation_for_chat(chat_id: int) -> tuple[Optional[dict], list[dict]]:
    """
    Return the clicked chat + the full conversation around it.
    Prefers the same session_id; falls back to all chats if session is missing.
    """
    chat = get_chat(chat_id)
    if not chat:
        return None, []

    session_id = chat.get("session_id")
    if session_id:
        return chat, get_session_chats(session_id)

    # Older rows without session_id: show full history so parents still see context
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM chats ORDER BY id ASC").fetchall()
    return chat, [dict(row) for row in rows]


def count_flagged_chats() -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM chats WHERE is_flagged = 1"
        ).fetchone()
    return int(row["n"] if row else 0)


def save_alert(
    child_message: str,
    category: str,
    severity: str,
    summary: str,
    parent_advice: str,
    chat_id: Optional[int] = None,
) -> dict:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO alerts
            (created_at, child_message, category, severity, summary, parent_advice, is_read, chat_id)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (_now(), child_message, category, severity, summary, parent_advice, chat_id),
        )
        conn.commit()
        alert_id = cur.lastrowid
    return {
        "id": alert_id,
        "created_at": _now(),
        "child_message": child_message,
        "category": category,
        "severity": severity,
        "summary": summary,
        "parent_advice": parent_advice,
        "is_read": 0,
        "chat_id": chat_id,
    }


def get_alerts(unread_only: bool = False, limit: int = 50) -> list[dict]:
    query = "SELECT * FROM alerts"
    if unread_only:
        query += " WHERE is_read = 0"
    query += " ORDER BY id DESC LIMIT ?"
    with _connect() as conn:
        rows = conn.execute(query, (limit,)).fetchall()
    return [dict(row) for row in rows]


def mark_alert_read(alert_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("UPDATE alerts SET is_read = 1 WHERE id = ?", (alert_id,))
        conn.commit()
        return cur.rowcount > 0
