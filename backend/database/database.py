"""All SQL lives here. No other module writes a query.

Design notes worth defending in a viva:

* Every query uses ``?`` parameters, never string formatting. That is what
  stops SQL injection; the input validator is a second layer, not the first.
* Each thread gets its own connection (``threading.local``). SQLite objects
  are not safe to share between threads, and one connection per thread avoids
  a global lock on every query.
* WAL mode lets the logging thread write while client threads read.
* Timestamps are stored as UTC ISO-8601 strings, so ordering is lexical and
  they survive a timezone change on the host.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_in(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


class DuplicateUserError(Exception):
    """Raised when a username is already taken."""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._local = threading.local()
        self._shared: Optional[sqlite3.Connection] = None
        self._shared_lock = threading.RLock()

        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    # ── connection plumbing ───────────────────────────────────────────────
    def connect(self) -> sqlite3.Connection:
        if self.path == ":memory:":
            # A single shared connection, guarded by a lock. Only used in tests.
            with self._shared_lock:
                if self._shared is None:
                    self._shared = self._new_connection()
                return self._shared

        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._new_connection()
            self._local.conn = conn
        return conn

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        if self.path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _write(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        conn = self.connect()
        if self.path == ":memory:":
            with self._shared_lock:
                return conn.execute(sql, tuple(params))
        return conn.execute(sql, tuple(params))

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        conn = self.connect()
        if self.path == ":memory:":
            with self._shared_lock:
                return conn.execute(sql, tuple(params)).fetchall()
        return conn.execute(sql, tuple(params)).fetchall()

    def _query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
        if self._shared is not None:
            self._shared.close()
            self._shared = None

    # ── schema ────────────────────────────────────────────────────────────
    def init_schema(self) -> None:
        sql = SCHEMA_FILE.read_text(encoding="utf-8")
        conn = self.connect()
        if self.path == ":memory:":
            with self._shared_lock:
                conn.executescript(sql)
        else:
            conn.executescript(sql)

    # ── users ─────────────────────────────────────────────────────────────
    def create_user(self, username: str, password_hash: str) -> int:
        try:
            cur = self._write(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, utc_now()),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateUserError(username) from exc
        return int(cur.lastrowid)

    def get_user_by_username(self, username: str) -> Optional[sqlite3.Row]:
        return self._query_one(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        )

    def get_user_by_id(self, user_id: int) -> Optional[sqlite3.Row]:
        return self._query_one("SELECT * FROM users WHERE user_id = ?", (user_id,))

    def get_all_users(self) -> list[sqlite3.Row]:
        return self._query("SELECT * FROM users ORDER BY username COLLATE NOCASE")

    def search_users(self, needle: str, limit: int = 20) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM users WHERE username LIKE ? COLLATE NOCASE "
            "ORDER BY username COLLATE NOCASE LIMIT ?",
            (f"%{needle}%", limit),
        )

    def touch_last_seen(self, user_id: int) -> None:
        self._write("UPDATE users SET last_seen_at = ? WHERE user_id = ?", (utc_now(), user_id))

    def count_users(self) -> int:
        row = self._query_one("SELECT COUNT(*) AS n FROM users")
        return int(row["n"]) if row else 0

    # ── sessions ──────────────────────────────────────────────────────────
    def create_session(self, user_id: int, token_hash: str, expires_at: str,
                       ip_address: Optional[str] = None) -> int:
        cur = self._write(
            "INSERT INTO sessions (user_id, token_hash, created_at, expires_at, ip_address) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, token_hash, utc_now(), expires_at, ip_address),
        )
        return int(cur.lastrowid)

    def get_session(self, token_hash: str) -> Optional[sqlite3.Row]:
        return self._query_one(
            "SELECT * FROM sessions WHERE token_hash = ? AND revoked_at IS NULL",
            (token_hash,),
        )

    def revoke_session(self, token_hash: str) -> bool:
        cur = self._write(
            "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (utc_now(), token_hash),
        )
        return cur.rowcount > 0

    def revoke_user_sessions(self, user_id: int) -> int:
        cur = self._write(
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (utc_now(), user_id),
        )
        return cur.rowcount

    def purge_expired_sessions(self) -> int:
        cur = self._write("DELETE FROM sessions WHERE expires_at < ?", (utc_now(),))
        return cur.rowcount

    # ── messages ──────────────────────────────────────────────────────────
    def save_message(self, sender_id: int, body: str, receiver_id: Optional[int] = None,
                     group_id: Optional[int] = None, status: str = "stored") -> int:
        cur = self._write(
            "INSERT INTO messages (sender_id, receiver_id, group_id, body, status, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sender_id, receiver_id, group_id, body, status, utc_now()),
        )
        return int(cur.lastrowid)

    def get_message(self, message_id: int) -> Optional[sqlite3.Row]:
        return self._query_one("SELECT * FROM messages WHERE message_id = ?", (message_id,))

    def set_message_status(self, message_id: int, status: str) -> None:
        extra = ", delivered_at = ?" if status in ("delivered", "read") else ""
        params: list[Any] = [status]
        if extra:
            params.append(utc_now())
        params.append(message_id)
        self._write(f"UPDATE messages SET status = ?{extra} WHERE message_id = ?", params)

    def get_conversation(self, user_a: int, user_b: int, limit: int = 50,
                         before_id: Optional[int] = None) -> list[sqlite3.Row]:
        sql = (
            "SELECT * FROM messages "
            "WHERE group_id IS NULL AND ("
            "  (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)"
            ") "
        )
        params: list[Any] = [user_a, user_b, user_b, user_a]
        if before_id is not None:
            sql += "AND message_id < ? "
            params.append(before_id)
        sql += "ORDER BY message_id DESC LIMIT ?"
        params.append(limit)
        rows = self._query(sql, params)
        return list(reversed(rows))

    def get_group_messages(self, group_id: int, limit: int = 50,
                           before_id: Optional[int] = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM messages WHERE group_id = ? "
        params: list[Any] = [group_id]
        if before_id is not None:
            sql += "AND message_id < ? "
            params.append(before_id)
        sql += "ORDER BY message_id DESC LIMIT ?"
        params.append(limit)
        rows = self._query(sql, params)
        return list(reversed(rows))

    def get_undelivered(self, user_id: int, limit: int = 100) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM messages WHERE receiver_id = ? AND status = 'stored' "
            "ORDER BY message_id ASC LIMIT ?",
            (user_id, limit),
        )

    def count_messages(self) -> int:
        row = self._query_one("SELECT COUNT(*) AS n FROM messages")
        return int(row["n"]) if row else 0

    # ── groups ────────────────────────────────────────────────────────────
    def create_group(self, name: str, owner_id: int) -> int:
        cur = self._write(
            "INSERT INTO groups (name, owner_id, created_at) VALUES (?, ?, ?)",
            (name, owner_id, utc_now()),
        )
        group_id = int(cur.lastrowid)
        self.add_group_member(group_id, owner_id)
        return group_id

    def add_group_member(self, group_id: int, user_id: int) -> bool:
        try:
            self._write(
                "INSERT INTO group_members (group_id, user_id, joined_at) VALUES (?, ?, ?)",
                (group_id, user_id, utc_now()),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_group_member(self, group_id: int, user_id: int) -> bool:
        cur = self._write(
            "DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id)
        )
        return cur.rowcount > 0

    def get_group(self, group_id: int) -> Optional[sqlite3.Row]:
        return self._query_one("SELECT * FROM groups WHERE group_id = ?", (group_id,))

    def get_group_members(self, group_id: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT u.user_id, u.username FROM group_members gm "
            "JOIN users u ON u.user_id = gm.user_id "
            "WHERE gm.group_id = ? ORDER BY u.username COLLATE NOCASE",
            (group_id,),
        )

    def is_group_member(self, group_id: int, user_id: int) -> bool:
        return self._query_one(
            "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        ) is not None

    def get_user_groups(self, user_id: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT g.* FROM groups g JOIN group_members gm ON gm.group_id = g.group_id "
            "WHERE gm.user_id = ? ORDER BY g.name COLLATE NOCASE",
            (user_id,),
        )

    # ── connection logs ───────────────────────────────────────────────────
    def log_connection(self, event_type: str, user_id: Optional[int] = None,
                       ip_address: Optional[str] = None, detail: Optional[str] = None) -> None:
        self._write(
            "INSERT INTO connection_logs (user_id, event_type, timestamp, ip_address, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, event_type, utc_now(), ip_address, detail),
        )

    def get_connection_logs(self, limit: int = 100,
                            event_type: Optional[str] = None) -> list[sqlite3.Row]:
        if event_type:
            return self._query(
                "SELECT * FROM connection_logs WHERE event_type = ? "
                "ORDER BY log_id DESC LIMIT ?",
                (event_type, limit),
            )
        return self._query(
            "SELECT * FROM connection_logs ORDER BY log_id DESC LIMIT ?", (limit,)
        )

    def count_logs(self) -> int:
        row = self._query_one("SELECT COUNT(*) AS n FROM connection_logs")
        return int(row["n"]) if row else 0
