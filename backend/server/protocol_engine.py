"""The protocol brain: one JSON request in, zero or more responses out.

Both front doors — the TLS socket server and the WebSocket bridge — call
``ProtocolEngine.handle(conn, request)`` and nothing else. That is what keeps
the two transports from drifting apart, and it means the frontend can switch
between them without the backend logic changing.

Every handler returns by sending through ``conn.send_json``. Handlers never
touch a socket directly, so they are trivially testable.
"""
from __future__ import annotations

from typing import Optional

import config
from authentication.auth import AuthService
from authentication.session_manager import SessionManager
from database.database import Database
from messaging.message_handler import MessageError, MessageHandler
from messaging.message_history import HistoryError, MessageHistory
from monitoring.logger import app_log, log_event
from monitoring.security_monitor import SecurityMonitor
from security.input_validation import (
    ValidationError, require, validate_group_id, validate_group_name, validate_int,
    validate_message_text, validate_token, validate_user_id, validate_username,
)
from server.connection_manager import Connection, ConnectionManager
from server.message_router import MessageRouter


class ProtocolError(Exception):
    def __init__(self, message: str, code: str = "invalid_request") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


AUTH_REQUIRED = {
    "private_message", "group_message", "get_users", "message_history",
    "typing", "delivery_ack", "logout", "create_group", "get_groups", "mark_read",
}

PUBLIC = {"register", "login", "ping", "resume_session", "server_info"}


class ProtocolEngine:
    def __init__(self, db: Database, auth: AuthService, sessions: SessionManager,
                 manager: ConnectionManager, handler: MessageHandler,
                 history: MessageHistory, router: MessageRouter,
                 monitor: SecurityMonitor) -> None:
        self.db = db
        self.auth = auth
        self.sessions = sessions
        self.manager = manager
        self.handler = handler
        self.history = history
        self.router = router
        self.monitor = monitor
        self._dispatch = {
            "register": self._register,
            "login": self._login,
            "resume_session": self._resume_session,
            "logout": self._logout,
            "private_message": self._private_message,
            "group_message": self._group_message,
            "get_users": self._get_users,
            "message_history": self._message_history,
            "typing": self._typing,
            "delivery_ack": self._delivery_ack,
            "mark_read": self._mark_read,
            "ping": self._ping,
            "create_group": self._create_group,
            "get_groups": self._get_groups,
            "server_info": self._server_info,
        }

    # ── entry point ───────────────────────────────────────────────────────
    def handle(self, conn: Connection, request: dict) -> None:
        msg_type = request.get("type")
        handler = self._dispatch.get(msg_type)
        if handler is None:
            self.monitor.suspicious_request(conn.id, conn.ip, f"unknown type {msg_type!r}")
            self._error(conn, "unknown_type", f"Unsupported message type: {msg_type}", msg_type)
            return

        if msg_type in AUTH_REQUIRED and not conn.authenticated:
            self._error(conn, "not_authenticated", "You must log in first", msg_type)
            return

        try:
            handler(conn, request)
        except ValidationError as exc:
            self.monitor.suspicious_request(conn.id, conn.ip, f"{exc.code}: {exc.message}")
            self._error(conn, exc.code, exc.message, msg_type)
        except (MessageError, HistoryError, ProtocolError) as exc:
            self._error(conn, exc.code, exc.message, msg_type)
        except Exception as exc:  # noqa: BLE001
            app_log().exception("Handler failed for %s", msg_type)
            self._error(conn, "server_error", "Internal server error", msg_type)

    # ── auth ──────────────────────────────────────────────────────────────
    def _register(self, conn: Connection, req: dict) -> None:
        require(req, "username", "password")
        username = validate_username(req["username"])
        password = req["password"]
        from security.input_validation import validate_password
        password = validate_password(password)

        result = self.auth.register(username, password, conn.ip)
        if not result.success:
            self._error(conn, result.error_code or "register_failed", result.message, "register")
            return

        conn.send_json({
            "type": "register_response",
            "success": True,
            "message": result.message,
            "user_id": result.user_id,
            "username": result.username,
        })

    def _login(self, conn: Connection, req: dict) -> None:
        require(req, "username", "password")
        username = str(req["username"]).strip()
        result = self.auth.login(username, req["password"], conn.ip)
        if not result.success:
            payload = {
                "type": "login_response",
                "success": False,
                "message": result.message,
                "code": result.error_code,
            }
            if result.retry_after:
                payload["retry_after"] = result.retry_after
            conn.send_json(payload)
            return

        self.manager.bind_user(conn, result.user_id, result.username, result.token)
        conn.send_json({
            "type": "login_response",
            "success": True,
            "message": result.message,
            "user_id": result.user_id,
            "username": result.username,
            "session_token": result.token,
            "expires_at": result.expires_at,
        })
        self._announce_presence()
        self.router.replay_undelivered(conn)

    def _resume_session(self, conn: Connection, req: dict) -> None:
        """Reconnect with a token instead of re-sending the password."""
        token = validate_token(req.get("session_token"))
        user_id = self.sessions.validate(token)
        if user_id is None:
            self._error(conn, "invalid_token", "Session expired or invalid", "resume_session")
            return
        user = self.db.get_user_by_id(user_id)
        if user is None:
            self._error(conn, "invalid_token", "Session no longer valid", "resume_session")
            return

        self.manager.bind_user(conn, user_id, user["username"], token)
        conn.send_json({
            "type": "resume_response",
            "success": True,
            "user_id": user_id,
            "username": user["username"],
            "message": "Session resumed",
        })
        self._announce_presence()
        self.router.replay_undelivered(conn)

    def _logout(self, conn: Connection, req: dict) -> None:
        self.auth.logout(conn.token, conn.user_id, conn.ip)
        log_event("LOGOUT", ip=conn.ip, user=conn.username)
        self.manager.unbind_user(conn)
        conn.send_json({"type": "logout_response", "success": True, "message": "Logged out"})
        self._announce_presence()

    # ── messaging ─────────────────────────────────────────────────────────
    def _private_message(self, conn: Connection, req: dict) -> None:
        self._reject_impersonation(conn, req)
        require(req, "message")
        receiver_id = validate_user_id(req.get("receiver_id"))
        text = validate_message_text(req["message"])

        message = self.handler.create_private(conn.user_id, receiver_id, text)
        outcome = self.router.route_private(message, conn)
        conn.send_json({
            "type": "message_response",
            "success": True,
            "message_id": message["message_id"],
            "receiver_id": receiver_id,
            "receiver": message["receiver_username"],
            "status": outcome["status"],
        })

    def _group_message(self, conn: Connection, req: dict) -> None:
        self._reject_impersonation(conn, req)
        require(req, "message", "group_id")
        group_id = validate_group_id(req["group_id"])
        text = validate_message_text(req["message"])

        message = self.handler.create_group_message(conn.user_id, group_id, text)
        outcome = self.router.route_group(message, conn)
        conn.send_json({
            "type": "message_response",
            "success": True,
            "message_id": message["message_id"],
            "group_id": group_id,
            "status": outcome["status"],
            "recipients": outcome["recipients"],
        })

    def _typing(self, conn: Connection, req: dict) -> None:
        if "receiver_id" not in req:
            raise ValidationError("Missing field: receiver_id", "missing_field")
        receiver_id = validate_user_id(req.get("receiver_id"))
        if not self.db.get_user_by_id(receiver_id):
            raise ValidationError("Recipient does not exist", "unknown_recipient")
        self.manager.send_to_user(receiver_id, {
            "type": "typing",
            "sender_id": conn.user_id,
            "sender": conn.username,
            "is_typing": bool(req.get("is_typing", True)),
        })

    def _delivery_ack(self, conn: Connection, req: dict) -> None:
        message_id = validate_int(req.get("message_id"), "message_id", 1, 2**31)
        row = self.db.get_message(message_id)
        if row is None:
            raise ProtocolError("Unknown message", "unknown_message")
        if row["receiver_id"] != conn.user_id:
            self.monitor.unauthorised_access(conn.username or "?", str(message_id), conn.ip)
            raise ProtocolError("Not your message", "not_your_message")
        self.handler.mark_delivered(message_id)
        self.manager.send_to_user(row["sender_id"], {
            "type": "delivery_ack",
            "message_id": message_id,
            "receiver_id": conn.user_id,
            "status": "delivered",
        })

    def _mark_read(self, conn: Connection, req: dict) -> None:
        message_id = validate_int(req.get("message_id"), "message_id", 1, 2**31)
        if not self.handler.mark_read(message_id, conn.user_id):
            raise ProtocolError("Cannot mark that message read", "not_your_message")
        row = self.db.get_message(message_id)
        if row is not None:
            self.manager.send_to_user(row["sender_id"], {
                "type": "read_receipt",
                "message_id": message_id,
                "reader_id": conn.user_id,
                "status": "read",
            })

    # ── queries ───────────────────────────────────────────────────────────
    def _get_users(self, conn: Connection, req: dict) -> None:
        online_ids = self.manager.online_user_ids()
        users = []
        for row in self.db.get_all_users():
            uid = int(row["user_id"])
            users.append({
                "user_id": uid,
                "username": row["username"],
                "status": "online" if uid in online_ids else "offline",
                "last_seen_at": row["last_seen_at"],
            })
        conn.send_json({
            "type": "users_response",
            "users": users,
            "online_count": len(online_ids),
        })

    def _message_history(self, conn: Connection, req: dict) -> None:
        limit = validate_int(req.get("limit", 50), "limit", 1, 200)
        before_id = req.get("before_id")
        before_id = (validate_int(before_id, "before_id", 1, 2**31)
                     if before_id is not None else None)

        if req.get("group_id") is not None:
            data = self.history.group(conn.user_id, validate_group_id(req["group_id"]),
                                      limit, before_id)
        else:
            if req.get("with_user_id") is None:
                raise ValidationError("Missing field: with_user_id or group_id", "missing_field")
            data = self.history.conversation(conn.user_id,
                                             validate_user_id(req["with_user_id"], "with_user_id"),
                                             limit, before_id)
        conn.send_json({"type": "history_response", "success": True, **data})

    def _create_group(self, conn: Connection, req: dict) -> None:
        require(req, "name")
        name = validate_group_name(req["name"])
        group_id = self.db.create_group(name, conn.user_id)
        for member in req.get("members", []) or []:
            try:
                member_id = validate_user_id(member, "member_id")
            except ValidationError:
                continue
            if self.db.get_user_by_id(member_id):
                self.db.add_group_member(group_id, member_id)
        conn.send_json({
            "type": "group_response",
            "success": True,
            "group_id": group_id,
            "name": name,
            "members": [m["username"] for m in self.db.get_group_members(group_id)],
        })

    def _get_groups(self, conn: Connection, req: dict) -> None:
        groups = []
        for row in self.db.get_user_groups(conn.user_id):
            groups.append({
                "group_id": row["group_id"],
                "name": row["name"],
                "owner_id": row["owner_id"],
                "members": [m["username"] for m in self.db.get_group_members(row["group_id"])],
            })
        conn.send_json({"type": "groups_response", "groups": groups})

    def _ping(self, conn: Connection, req: dict) -> None:
        from database.database import utc_now
        conn.send_json({"type": "pong", "server_time": utc_now()})

    def _server_info(self, conn: Connection, req: dict) -> None:
        conn.send_json({
            "type": "server_info_response",
            "name": "CipherChat",
            "version": "1.0.0",
            "tls": conn.transport != "tcp-plain",
            "transport": conn.transport,
            "max_message_chars": config.MAX_MESSAGE_CHARS,
            "max_frame_bytes": config.MAX_FRAME_BYTES,
            "stats": self.manager.stats(),
            "security": self.monitor.snapshot()["counters"],
        })

    # ── presence ──────────────────────────────────────────────────────────
    def announce_presence(self) -> None:
        self._announce_presence()

    def _announce_presence(self) -> None:
        online = []
        for user_id in self.manager.online_user_ids():
            conns = self.manager.connections_for(user_id)
            if conns:
                online.append({"user_id": user_id, "username": conns[0].username})
        self.manager.broadcast({
            "type": "presence",
            "online": online,
            "online_count": len(online),
        })

    # ── helpers ───────────────────────────────────────────────────────────
    def _reject_impersonation(self, conn: Connection, req: dict) -> None:
        """The client may not claim to be someone else.

        ``sender`` is accepted in the payload only so we can detect and log a
        forgery attempt; identity always comes from the authenticated session.
        """
        claimed = req.get("sender") or req.get("sender_id")
        if claimed is None:
            return
        if str(claimed) not in {str(conn.user_id), str(conn.username)}:
            self.monitor.impersonation_attempt(str(claimed), str(conn.username), conn.ip)
            raise ProtocolError(
                "Sender identity does not match the authenticated session",
                "impersonation_rejected",
            )

    def _error(self, conn: Connection, code: str, message: str,
               request_type: Optional[str] = None) -> None:
        conn.send_json({
            "type": "error",
            "code": code,
            "message": message,
            "request_type": request_type,
        })
