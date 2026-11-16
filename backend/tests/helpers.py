"""Shared test fixtures: a fake connection and a fully wired engine.

Tests run against the real database and the real engine — only the socket is
faked. That way a bug in routing or validation is caught, without the flakiness
of real ports in every test.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from authentication.auth import AuthService
from authentication.session_manager import SessionManager
from database.database import Database
from messaging.message_handler import MessageHandler
from messaging.message_history import MessageHistory
from monitoring.security_monitor import SecurityMonitor
from security.rate_limiter import RateLimiter
from server.connection_manager import Connection, ConnectionManager
from server.message_router import MessageRouter
from server.protocol_engine import ProtocolEngine


class FakeConnection(Connection):
    def __init__(self, addr=("127.0.0.1", 1234), transport="tcp") -> None:
        super().__init__(addr, transport)
        self.sent: list[dict] = []

    def send_json(self, payload: dict) -> bool:
        if self.closed:
            return False
        self.sent.append(payload)
        return True

    def close(self) -> None:
        self.closed = True

    # ── test helpers ──────────────────────────────────────────────────────
    def last(self, msg_type: str | None = None) -> dict:
        for payload in reversed(self.sent):
            if msg_type is None or payload.get("type") == msg_type:
                return payload
        raise AssertionError(f"no {msg_type or 'message'} was sent; got "
                             f"{[p.get('type') for p in self.sent]}")

    def clear(self) -> None:
        self.sent.clear()

    def types(self) -> list[str]:
        return [p.get("type") for p in self.sent]


class EngineTestCase(unittest.TestCase):
    """Gives every test a fresh database and a wired engine."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmpdir.name) / "test.db")
        self.db.init_schema()

        self.sessions = SessionManager(self.db)
        self.limiter = RateLimiter()
        self.monitor = SecurityMonitor()
        self.auth = AuthService(self.db, self.sessions, self.limiter, self.monitor)
        self.manager = ConnectionManager(max_clients=50)
        self.handler = MessageHandler(self.db)
        self.history = MessageHistory(self.db)
        self.router = MessageRouter(self.manager, self.db)
        self.engine = ProtocolEngine(
            db=self.db, auth=self.auth, sessions=self.sessions, manager=self.manager,
            handler=self.handler, history=self.history, router=self.router,
            monitor=self.monitor,
        )

    def tearDown(self) -> None:
        self.db.close()
        self.tmpdir.cleanup()

    # ── helpers ───────────────────────────────────────────────────────────
    def make_user(self, username: str, password: str = "TestPass123") -> FakeConnection:
        """Register + log in a fake client, returning its connection."""
        conn = FakeConnection()
        self.manager.add(conn)
        self.engine.handle(conn, {"type": "register", "username": username,
                                  "password": password})
        self.engine.handle(conn, {"type": "login", "username": username,
                                  "password": password})
        self.assertTrue(conn.authenticated, f"{username} did not log in")
        conn.clear()
        return conn

    def user_id(self, username: str) -> int:
        row = self.db.get_user_by_username(username)
        self.assertIsNotNone(row, f"{username} not in database")
        return int(row["user_id"])
