"""History retrieval and shaping for the frontend.

Pagination is by ``before_id`` rather than offset: message IDs are stable and
monotonic, so "give me the 50 messages before id 501" stays correct even while
new messages arrive, which OFFSET does not.
"""
from __future__ import annotations

from database.database import Database
from security.input_validation import ValidationError, validate_int


class HistoryError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class MessageHistory:
    def __init__(self, db: Database) -> None:
        self.db = db

    def conversation(self, user_id: int, other_id: int, limit: int = 50,
                     before_id: int | None = None) -> dict:
        try:
            limit = validate_int(limit, "limit", minimum=1, maximum=200)
            if before_id is not None:
                before_id = validate_int(before_id, "before_id", minimum=1, maximum=2**31)
        except ValidationError as exc:
            raise HistoryError(exc.message, exc.code) from exc

        other = self.db.get_user_by_id(other_id)
        if other is None:
            raise HistoryError("User does not exist", "unknown_recipient")

        rows = self.db.get_conversation(user_id, other_id, limit, before_id)
        return {
            "with_user_id": other_id,
            "with_username": other["username"],
            "messages": [self._serialise(row) for row in rows],
            "count": len(rows),
        }

    def group(self, user_id: int, group_id: int, limit: int = 50,
              before_id: int | None = None) -> dict:
        if not self.db.is_group_member(group_id, user_id):
            raise HistoryError("You are not a member of this group", "not_a_member")
        limit = validate_int(limit, "limit", minimum=1, maximum=200)
        rows = self.db.get_group_messages(group_id, limit, before_id)
        return {
            "group_id": group_id,
            "messages": [self._serialise(row) for row in rows],
            "count": len(rows),
        }

    def _serialise(self, row) -> dict:
        sender = self.db.get_user_by_id(row["sender_id"])
        return {
            "message_id": row["message_id"],
            "sender_id": row["sender_id"],
            "sender": sender["username"] if sender else "unknown",
            "receiver_id": row["receiver_id"],
            "group_id": row["group_id"],
            "message": row["body"],
            "status": row["status"],
            "timestamp": row["timestamp"],
        }
