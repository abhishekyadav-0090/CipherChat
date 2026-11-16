"""Who is connected right now, and how to reach them.

One rule makes the rest of the backend safe: every mutation of the registries
happens while holding ``self._lock``. Threads accept, disconnect and route
messages at the same time; without the lock two threads can edit the same dict
and one update vanishes (a lost client) or the dict is left half-updated.

A user may be connected from more than one device, so a user maps to a *set* of
connections, not a single socket. That is what makes "logged in on a phone and
a laptop" work instead of silently kicking one off.
"""
from __future__ import annotations

import itertools
import threading
from typing import Any, Iterable, Optional


class Connection:
    """Transport-neutral connection. Subclassed by TCP and WebSocket."""

    _counter = itertools.count(1)

    def __init__(self, addr: Any, transport: str) -> None:
        self.id = f"{transport}-{next(self._counter)}"
        self.addr = addr
        self.transport = transport
        self.user_id: Optional[int] = None
        self.username: Optional[str] = None
        self.token: Optional[str] = None
        self.closed = False
        self.sent_frames = 0
        self.received_frames = 0

    @property
    def ip(self) -> str:
        if isinstance(self.addr, tuple) and self.addr:
            return str(self.addr[0])
        return str(self.addr)

    @property
    def authenticated(self) -> bool:
        return self.user_id is not None

    def describe(self) -> str:
        if self.username:
            return f"{self.username}@{self.ip}({self.transport})"
        return f"anonymous@{self.ip}({self.transport})"

    # ── to be implemented by each transport ───────────────────────────────
    def send_json(self, payload: dict) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class ConnectionManager:
    def __init__(self, max_clients: int = 200) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, Connection] = {}
        self._by_user: dict[int, set[str]] = {}
        self.max_clients = max_clients
        self.total_accepted = 0
        self.total_rejected = 0

    # ── lifecycle ─────────────────────────────────────────────────────────
    def add(self, conn: Connection) -> bool:
        with self._lock:
            if len(self._by_id) >= self.max_clients:
                self.total_rejected += 1
                return False
            self._by_id[conn.id] = conn
            self.total_accepted += 1
            return True

    def remove(self, conn: Connection) -> Optional[Connection]:
        """Unregister. Returns the conn if it was actually present."""
        with self._lock:
            existing = self._by_id.pop(conn.id, None)
            if conn.user_id is not None:
                ids = self._by_user.get(conn.user_id)
                if ids is not None:
                    ids.discard(conn.id)
                    if not ids:
                        self._by_user.pop(conn.user_id, None)
            return existing

    def bind_user(self, conn: Connection, user_id: int, username: str,
                  token: Optional[str] = None) -> None:
        with self._lock:
            # If this connection was bound to someone else, unbind first.
            if conn.user_id is not None and conn.user_id != user_id:
                self.unbind_user(conn)
            conn.user_id = user_id
            conn.username = username
            conn.token = token
            self._by_user.setdefault(user_id, set()).add(conn.id)

    def unbind_user(self, conn: Connection) -> None:
        with self._lock:
            if conn.user_id is not None:
                ids = self._by_user.get(conn.user_id)
                if ids is not None:
                    ids.discard(conn.id)
                    if not ids:
                        self._by_user.pop(conn.user_id, None)
            conn.user_id = None
            conn.username = None
            conn.token = None

    # ── lookups ───────────────────────────────────────────────────────────
    def get(self, conn_id: str) -> Optional[Connection]:
        with self._lock:
            return self._by_id.get(conn_id)

    def connections_for(self, user_id: int) -> list[Connection]:
        with self._lock:
            ids = list(self._by_user.get(user_id, ()))
            return [self._by_id[i] for i in ids if i in self._by_id]

    def is_online(self, user_id: int) -> bool:
        with self._lock:
            return bool(self._by_user.get(user_id))

    def online_user_ids(self) -> set[int]:
        with self._lock:
            return set(self._by_user.keys())

    def all_connections(self) -> list[Connection]:
        with self._lock:
            return list(self._by_id.values())

    def authenticated_connections(self) -> list[Connection]:
        with self._lock:
            return [c for c in self._by_id.values() if c.authenticated]

    def count(self) -> int:
        with self._lock:
            return len(self._by_id)

    def count_for_user(self, user_id: int) -> int:
        with self._lock:
            return len(self._by_user.get(user_id, ()))

    # ── sending ───────────────────────────────────────────────────────────
    def send_to_user(self, user_id: int, payload: dict) -> int:
        """Send to every live connection of a user. Returns how many succeeded."""
        sent = 0
        for conn in self.connections_for(user_id):
            if conn.send_json(payload):
                sent += 1
        return sent

    def broadcast(self, payload: dict, exclude: Iterable[str] = (),
                  authenticated_only: bool = True) -> int:
        excluded = set(exclude)
        sent = 0
        targets = (self.authenticated_connections() if authenticated_only
                   else self.all_connections())
        for conn in targets:
            if conn.id in excluded:
                continue
            if conn.send_json(payload):
                sent += 1
        return sent

    def stats(self) -> dict:
        with self._lock:
            return {
                "connections": len(self._by_id),
                "users_online": len(self._by_user),
                "max_clients": self.max_clients,
                "total_accepted": self.total_accepted,
                "total_rejected": self.total_rejected,
            }
