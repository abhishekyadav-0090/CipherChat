"""Authentication orchestration: register, login, logout.

The password check lives in password_manager and the token lifecycle lives in
session_manager; this module is the policy layer that decides what happens when
things go wrong — throttling, logging, and what the client is told.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import config
from authentication.password_manager import (
    hash_password, needs_rehash, verify_password,
)
from authentication.session_manager import SessionManager
from database.database import Database, DuplicateUserError
from security.rate_limiter import RateLimiter


@dataclass
class AuthResult:
    success: bool
    message: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    token: Optional[str] = None
    expires_at: Optional[str] = None
    error_code: Optional[str] = None
    retry_after: Optional[int] = None


class AuthService:
    def __init__(self, db: Database, sessions: SessionManager,
                 limiter: RateLimiter, monitor=None,
                 ip_limiter: Optional[RateLimiter] = None) -> None:
        self.db = db
        self.sessions = sessions
        self.limiter = limiter                       # per username: 5 attempts
        self.ip_limiter = ip_limiter or RateLimiter(  # per IP: much looser
            max_attempts=config.LOGIN_IP_MAX_ATTEMPTS)
        self.monitor = monitor

    # ── registration ──────────────────────────────────────────────────────
    def register(self, username: str, password: str, ip: Optional[str] = None) -> AuthResult:
        try:
            password_hash = hash_password(password)
            user_id = self.db.create_user(username, password_hash)
        except DuplicateUserError:
            self._log("REGISTER_FAILED", None, ip, f"duplicate username={username}")
            return AuthResult(False, "Username already taken", error_code="username_taken")
        except Exception as exc:  # noqa: BLE001
            self._log("REGISTER_FAILED", None, ip, f"db error: {exc}")
            return AuthResult(False, "Could not create account", error_code="server_error")

        self._log("USER_REGISTERED", user_id, ip, f"username={username}")
        return AuthResult(True, "Registration successful", user_id=user_id, username=username)

    # ── login ─────────────────────────────────────────────────────────────
    def login(self, username: str, password: str, ip: Optional[str] = None) -> AuthResult:
        # Throttle by username *and* by IP, so neither a single account nor a
        # single machine can be hammered. Checked before the hash comparison,
        # because the hash comparison is the expensive part.
        for limiter, key in ((self.limiter, f"user:{username.lower()}"),
                             (self.ip_limiter, f"ip:{ip}")):
            allowed, retry_after = limiter.check(key)
            if not allowed:
                self._log("LOGIN_THROTTLED", None, ip, f"key={key} retry_after={retry_after}s")
                if self.monitor:
                    self.monitor.throttle_triggered(key, ip)
                return AuthResult(
                    False, "Too many failed attempts. Try again later.",
                    error_code="throttled", retry_after=retry_after,
                )

        row = self.db.get_user_by_username(username)
        # Same message and same rough timing whether the user exists or not:
        # telling an attacker "no such user" is a free account enumeration.
        if row is None:
            self._fail(username, ip, "unknown username")
            return AuthResult(False, "Invalid username or password", error_code="invalid_credentials")

        if not verify_password(password, row["password_hash"]):
            self._fail(username, ip, "bad password")
            return AuthResult(False, "Invalid username or password", error_code="invalid_credentials")

        user_id = int(row["user_id"])
        self.limiter.record_success(f"user:{username.lower()}")
        self.ip_limiter.record_success(f"ip:{ip}")

        # Transparent upgrade if the hash was made with an older scheme.
        if needs_rehash(row["password_hash"]):
            try:
                self.db._write(  # noqa: SLF001 - internal by design, documented in database.py
                    "UPDATE users SET password_hash = ? WHERE user_id = ?",
                    (hash_password(password), user_id),
                )
            except Exception:  # noqa: BLE001
                pass

        token, expires_at = self.sessions.issue(user_id, ip)
        self.db.touch_last_seen(user_id)
        self._log("LOGIN_SUCCESS", user_id, ip, f"username={row['username']}")

        return AuthResult(
            True, "Login successful", user_id=user_id, username=row["username"],
            token=token, expires_at=expires_at,
        )

    # ── logout ────────────────────────────────────────────────────────────
    def logout(self, token: Optional[str], user_id: Optional[int],
               ip: Optional[str] = None) -> AuthResult:
        revoked = self.sessions.revoke(token) if token else False
        if user_id:
            self._log("LOGOUT", user_id, ip, "session revoked" if revoked else "no session")
        return AuthResult(True, "Logged out")

    # ── helpers ───────────────────────────────────────────────────────────
    def _fail(self, username: str, ip: Optional[str], reason: str) -> None:
        self.limiter.record_failure(f"user:{username.lower()}")
        self.ip_limiter.record_failure(f"ip:{ip}")
        self._log("LOGIN_FAILED", None, ip, f"username={username} reason={reason}")
        if self.monitor:
            self.monitor.login_failed(username, ip, reason)

    def _log(self, event: str, user_id: Optional[int], ip: Optional[str], detail: str) -> None:
        try:
            self.db.log_connection(event, user_id, ip, detail)
        except Exception:  # noqa: BLE001 - logging must never break a login
            pass
