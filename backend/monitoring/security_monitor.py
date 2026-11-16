"""Security event tracking on top of the logger.

Counters live in memory so the dashboard can ask "how many failed logins since
startup?" without parsing a log file, and every event is also written to
security.log for the report and for the viva.
"""
from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timezone

from monitoring.logger import log_security


class SecurityMonitor:
    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()
        self._lock = threading.Lock()
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.recent: list[dict] = []
        self.max_recent = 100

    # ── events ────────────────────────────────────────────────────────────
    def login_failed(self, username: str, ip: str | None, reason: str) -> None:
        self._record("login_failed", username=username, ip=ip, detail=reason)

    def throttle_triggered(self, key: str, ip: str | None) -> None:
        self._record("throttle_triggered", ip=ip, detail=key)

    def suspicious_request(self, conn_id: str, ip: str | None, reason: str) -> None:
        self._record("suspicious_request", ip=ip, detail=f"{conn_id}: {reason}")

    def impersonation_attempt(self, claimed: str, actual: str, ip: str | None) -> None:
        self._record("impersonation_attempt", ip=ip,
                     detail=f"claimed={claimed} actual={actual}")

    def unauthorised_access(self, user: str, target: str, ip: str | None) -> None:
        self._record("unauthorised_access", user=user, ip=ip, detail=f"target={target}")

    def oversized_frame(self, ip: str | None, size: int) -> None:
        self._record("oversized_frame", ip=ip, detail=f"bytes={size}")

    def malformed_frame(self, ip: str | None, reason: str) -> None:
        self._record("malformed_frame", ip=ip, detail=reason)

    # ── reporting ─────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "started_at": self.started_at,
                "counters": dict(self._counts),
                "recent": list(self.recent[-20:]),
            }

    def summary_line(self) -> str:
        snap = self.snapshot()
        if not snap["counters"]:
            return "no security events"
        return ", ".join(f"{k}={v}" for k, v in sorted(snap["counters"].items()))

    # ── internals ─────────────────────────────────────────────────────────
    def _record(self, event: str, **fields) -> None:
        with self._lock:
            self._counts[event] += 1
            self.recent.append({
                "event": event,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                **fields,
            })
            if len(self.recent) > self.max_recent:
                self.recent = self.recent[-self.max_recent:]
        log_security(event.upper(), detail=str(fields.get("detail", "")),
                     ip=fields.get("ip"), user=fields.get("username") or fields.get("user"))
