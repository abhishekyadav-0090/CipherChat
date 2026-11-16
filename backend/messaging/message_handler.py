"""Business logic for creating messages.

This module decides *whether* a message may exist: does the recipient exist,
is the sender allowed into the group, is the body acceptable. It does not know
how a message reaches a socket — that is message_router's job. Keeping the two
apart is what lets the same code serve the TCP server and the WebSocket bridge.
"""
from __future__ import annotations

from typing import Optional

from database.database import Database
from security.input_validation import ValidationError, validate_message_text


class MessageError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class MessageHandler:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ── private ───────────────────────────────────────────────────────────
    def create_private(self, sender_id: int, receiver_id: int, text: str) -> dict:
        if sender_id == receiver_id:
            raise MessageError("You cannot message yourself", "self_message")

        receiver = self.db.get_user_by_id(receiver_id)
        if receiver is None:
            raise MessageError("Recipient does not exist", "unknown_recipient")

        body = validate_message_text(text)
        message_id = self.db.save_message(
            sender_id=sender_id, body=body, receiver_id=receiver_id, status="stored",
        )
        return {
            "message_id": message_id,
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "receiver_username": receiver["username"],
            "body": body,
            "status": "stored",
        }

    # ── group ─────────────────────────────────────────────────────────────
    def create_group_message(self, sender_id: int, group_id: int, text: str) -> dict:
        group = self.db.get_group(group_id)
        if group is None:
            raise MessageError("Group does not exist", "unknown_group")
        if not self.db.is_group_member(group_id, sender_id):
            # Authorisation belongs on the server. A client asking nicely is
            # not a permission.
            raise MessageError("You are not a member of this group", "not_a_member")

        body = validate_message_text(text)
        message_id = self.db.save_message(
            sender_id=sender_id, body=body, group_id=group_id, status="stored",
        )
        return {
            "message_id": message_id,
            "sender_id": sender_id,
            "group_id": group_id,
            "group_name": group["name"],
            "body": body,
            "status": "stored",
        }

    # ── status ────────────────────────────────────────────────────────────
    def mark_delivered(self, message_id: int) -> bool:
        row = self.db.get_message(message_id)
        if row is None:
            return False
        self.db.set_message_status(message_id, "delivered")
        return True

    def mark_read(self, message_id: int, reader_id: int) -> bool:
        row = self.db.get_message(message_id)
        if row is None or row["receiver_id"] != reader_id:
            # Only the recipient may mark a message read.
            return False
        self.db.set_message_status(message_id, "read")
        return True

    def undelivered_for(self, user_id: int) -> list[dict]:
        rows = self.db.get_undelivered(user_id)
        return [self._serialise(row) for row in rows]

    def _serialise(self, row) -> dict:
        sender = self.db.get_user_by_id(row["sender_id"])
        return {
            "message_id": row["message_id"],
            "sender_id": row["sender_id"],
            "sender": sender["username"] if sender else "unknown",
            "receiver_id": row["receiver_id"],
            "group_id": row["group_id"],
            "body": row["body"],
            "status": row["status"],
            "timestamp": row["timestamp"],
        }

    @staticmethod
    def validate_text(text: str) -> str:
        try:
            return validate_message_text(text)
        except ValidationError as exc:
            raise MessageError(exc.message, exc.code) from exc
