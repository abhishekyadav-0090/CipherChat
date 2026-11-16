"""Session tokens.

Two rules that carry most of the security here:

1. The client gets a random token. The database only ever stores its SHA-256
   hash, so a leaked database file cannot be replayed as live sessions.
2. A token is checked against ``expires_at`` and ``revoked_at`` on every use,
   so logout and expiry are enforced server-side, not by the client politely
   forgetting the token.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

import config
from authentication.password_manager import random_token
from database.database import Database


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _expired(expires_at: str) -> bool:
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry <= datetime.now(timezone.utc)


class SessionManager:
    def __init__(self, db: Database, ttl_seconds: int = config.SESSION_TTL_SECONDS) -> None:
        self.db = db
        self.ttl_seconds = ttl_seconds

    def issue(self, user_id: int, ip_address: Optional[str] = None) -> tuple[str, str]:
        """Create a session. Returns (plaintext token, expiry ISO string)."""
        from database.database import utc_in  # local import keeps module import cheap

        token = random_token()
        expires_at = utc_in(self.ttl_seconds)
        self.db.create_session(user_id, hash_token(token), expires_at, ip_address)
        return token, expires_at

    def validate(self, token: str) -> Optional[int]:
        """Return the user_id for a live token, else None."""
        if not token or not isinstance(token, str):
            return None
        row = self.db.get_session(hash_token(token))
        if row is None:
            return None
        if _expired(row["expires_at"]):
            self.db.revoke_session(hash_token(token))
            return None
        return int(row["user_id"])

    def revoke(self, token: str) -> bool:
        if not token:
            return False
        return self.db.revoke_session(hash_token(token))

    def revoke_all(self, user_id: int) -> int:
        return self.db.revoke_user_sessions(user_id)

    def cleanup(self) -> int:
        return self.db.purge_expired_sessions()
