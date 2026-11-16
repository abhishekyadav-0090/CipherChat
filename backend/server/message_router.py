"""Delivery: take a persisted message and put it on the right sockets.

Persist first, deliver second. If the process dies between the two, the message
is still in the database and is replayed the next time the recipient logs in.
Delivering first and saving second is how a chat app loses messages.

Offline recipients are not an error. The message stays ``stored`` and is handed
over on next login — that is the whole point of the status column.
"""
from __future__ import annotations

from database.database import Database
from monitoring.logger import app_log, log_event
from server.connection_manager import Connection, ConnectionManager


class MessageRouter:
    def __init__(self, manager: ConnectionManager, db: Database) -> None:
        self.manager = manager
        self.db = db

    # ── private ───────────────────────────────────────────────────────────
    def route_private(self, message: dict, sender_conn: Connection) -> dict:
        payload = {
            "type": "incoming_message",
            "message_id": message["message_id"],
            "sender_id": message["sender_id"],
            "sender": sender_conn.username,
            "receiver_id": message["receiver_id"],
            "message": message["body"],
            "status": "delivered",
            "timestamp": self._timestamp(message["message_id"]),
        }
        delivered = self.manager.send_to_user(message["receiver_id"], payload) > 0
        if delivered:
            self.db.set_message_status(message["message_id"], "delivered")
        log_event("MESSAGE_ROUTED",
                  detail=(f"id={message['message_id']} to={message['receiver_username']} "
                          f"{'delivered' if delivered else 'stored (offline)'}"),
                  ip=sender_conn.ip, user=sender_conn.username)
        return {"delivered": delivered, "status": "delivered" if delivered else "stored"}

    # ── group ─────────────────────────────────────────────────────────────
    def route_group(self, message: dict, sender_conn: Connection) -> dict:
        members = self.db.get_group_members(message["group_id"])
        payload = {
            "type": "incoming_group_message",
            "message_id": message["message_id"],
            "group_id": message["group_id"],
            "group_name": message.get("group_name"),
            "sender_id": message["sender_id"],
            "sender": sender_conn.username,
            "message": message["body"],
            "timestamp": self._timestamp(message["message_id"]),
        }
        reached = 0
        for member in members:
            member_id = int(member["user_id"])
            if member_id == message["sender_id"]:
                continue
            if self.manager.send_to_user(member_id, payload) > 0:
                reached += 1
        log_event("GROUP_MESSAGE_ROUTED",
                  detail=f"id={message['message_id']} group={message['group_id']} reached={reached}",
                  ip=sender_conn.ip, user=sender_conn.username)
        return {"delivered": reached > 0, "recipients": reached,
                "status": "delivered" if reached else "stored"}

    # ── replay ────────────────────────────────────────────────────────────
    def replay_undelivered(self, conn: Connection, limit: int = 100) -> int:
        """Push everything that arrived while this user was offline."""
        if conn.user_id is None:
            return 0
        rows = self.db.get_undelivered(conn.user_id, limit)
        count = 0
        for row in rows:
            sender = self.db.get_user_by_id(row["sender_id"])
            conn.send_json({
                "type": "incoming_message",
                "message_id": row["message_id"],
                "sender_id": row["sender_id"],
                "sender": sender["username"] if sender else "unknown",
                "receiver_id": row["receiver_id"],
                "message": row["body"],
                "status": "delivered",
                "timestamp": row["timestamp"],
                "offline_replay": True,
            })
            self.db.set_message_status(row["message_id"], "delivered")
            count += 1
        if count:
            app_log().info("REPLAYED %s offline message(s) to %s", count, conn.username)
        return count

    # ── helpers ───────────────────────────────────────────────────────────
    def _timestamp(self, message_id: int) -> str:
        row = self.db.get_message(message_id)
        return row["timestamp"] if row else ""
