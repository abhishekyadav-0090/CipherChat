"""Typed views over database rows.

The database layer hands back plain ``sqlite3.Row`` objects; these dataclasses
are the shape the rest of the backend passes around, so a column rename in
``schema.sql`` breaks in one place instead of everywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional


@dataclass(frozen=True)
class User:
    user_id: int
    username: str
    password_hash: str
    created_at: str
    last_seen_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> "User":
        return cls(
            user_id=row["user_id"],
            username=row["username"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            last_seen_at=row["last_seen_at"],
        )

    def public(self) -> dict:
        """The only safe way to hand a user to a client: no hash, ever."""
        return {"user_id": self.user_id, "username": self.username}


@dataclass(frozen=True)
class Message:
    message_id: int
    sender_id: int
    receiver_id: Optional[int]
    group_id: Optional[int]
    body: str
    status: str
    timestamp: str

    @classmethod
    def from_row(cls, row: Any) -> "Message":
        return cls(
            message_id=row["message_id"],
            sender_id=row["sender_id"],
            receiver_id=row["receiver_id"],
            group_id=row["group_id"],
            body=row["body"],
            status=row["status"],
            timestamp=row["timestamp"],
        )

    def as_dict(self, sender_username: Optional[str] = None) -> dict:
        data = asdict(self)
        if sender_username is not None:
            data["sender"] = sender_username
        return data


@dataclass(frozen=True)
class Session:
    session_id: int
    user_id: int
    token_hash: str
    created_at: str
    expires_at: str
    ip_address: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> "Session":
        return cls(
            session_id=row["session_id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            ip_address=row["ip_address"],
        )


@dataclass(frozen=True)
class Group:
    group_id: int
    name: str
    owner_id: int
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> "Group":
        return cls(
            group_id=row["group_id"],
            name=row["name"],
            owner_id=row["owner_id"],
            created_at=row["created_at"],
        )
