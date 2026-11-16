"""Sliding-window rate limiting, used for login throttling.

Deliberately in-memory and dependency-free: at this scale (one class project,
one server process) a dict of timestamps is the right tool. The trade-off to
state out loud in a viva is that counters reset when the server restarts, and
they are per-process — a real deployment would keep them in Redis.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Optional

import config


class RateLimiter:
    def __init__(self, max_attempts: int = config.LOGIN_MAX_ATTEMPTS,
                 window_seconds: int = config.LOGIN_WINDOW_SECONDS,
                 lockout_seconds: int = config.LOGIN_LOCKOUT_SECONDS,
                 clock=time.monotonic) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._clock = clock
        self._failures: dict[str, Deque[float]] = defaultdict(deque)
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    # ── public API ────────────────────────────────────────────────────────
    def check(self, key: str) -> tuple[bool, Optional[int]]:
        """(allowed, retry_after_seconds)."""
        now = self._clock()
        with self._lock:
            until = self._locked_until.get(key)
            if until is not None:
                if until > now:
                    return False, int(until - now) + 1
                # Lockout served: clear it and start a fresh window.
                self._locked_until.pop(key, None)
                self._failures.pop(key, None)
            return True, None

    def record_failure(self, key: str) -> int:
        """Record a failed attempt. Returns the count inside the window."""
        now = self._clock()
        with self._lock:
            bucket = self._failures[key]
            bucket.append(now)
            self._prune(bucket, now)
            count = len(bucket)
            if count >= self.max_attempts:
                self._locked_until[key] = now + self.lockout_seconds
            return count

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def is_blocked(self, key: str) -> bool:
        allowed, _ = self.check(key)
        return not allowed

    def failure_count(self, key: str) -> int:
        now = self._clock()
        with self._lock:
            bucket = self._failures.get(key)
            if not bucket:
                return 0
            self._prune(bucket, now)
            return len(bucket)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()

    def prune_all(self) -> None:
        now = self._clock()
        with self._lock:
            for key in list(self._failures):
                self._prune(self._failures[key], now)
                if not self._failures[key]:
                    self._failures.pop(key, None)

    # ── internals ─────────────────────────────────────────────────────────
    def _prune(self, bucket: Deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
