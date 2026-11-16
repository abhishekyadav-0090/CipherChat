"""Every byte that arrives from a client passes through here first.

The rule: nothing outside this module trusts a client-supplied value. A
validator either returns a clean value or raises ValidationError with a code
the protocol documents, so the frontend can react without guessing.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Iterable

import config

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
CONTROL_CHARS = "".join(chr(c) for c in range(0, 32) if chr(c) not in "\n\t")
CONTROL_RE = re.compile(f"[{re.escape(CONTROL_CHARS)}]")


class ValidationError(Exception):
    def __init__(self, message: str, code: str = "invalid_request") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ── frame level ───────────────────────────────────────────────────────────
def parse_frame(raw: bytes) -> dict:
    """Decode one JSON frame into a dict, enforcing size and shape."""
    if not raw:
        raise ValidationError("Empty frame", "empty_frame")
    if len(raw) > config.MAX_FRAME_BYTES:
        raise ValidationError("Frame too large", "frame_too_large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("Frame is not valid UTF-8", "bad_encoding") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("Malformed JSON", "malformed_json") from exc
    if not isinstance(data, dict):
        raise ValidationError("Frame must be a JSON object", "bad_shape")
    if "type" not in data or not isinstance(data.get("type"), str):
        raise ValidationError("Missing message type", "missing_type")
    return data


def require(data: dict, *fields: str) -> None:
    missing = [f for f in fields if data.get(f) in (None, "")]
    if missing:
        raise ValidationError(f"Missing field(s): {', '.join(missing)}", "missing_field")


# ── field level ───────────────────────────────────────────────────────────
def validate_username(username: Any) -> str:
    if not isinstance(username, str):
        raise ValidationError("Username must be text", "bad_username")
    username = username.strip()
    if len(username) < config.MIN_USERNAME_LEN:
        raise ValidationError(
            f"Username must be at least {config.MIN_USERNAME_LEN} characters", "bad_username")
    if len(username) > config.MAX_USERNAME_LEN:
        raise ValidationError(
            f"Username must be at most {config.MAX_USERNAME_LEN} characters", "bad_username")
    if not USERNAME_RE.match(username):
        raise ValidationError(
            "Username must start with a letter and use only letters, digits and _",
            "bad_username")
    if username.lower() in config.RESERVED_USERNAMES:
        raise ValidationError("That username is reserved", "username_reserved")
    return username


def validate_password(password: Any) -> str:
    if not isinstance(password, str):
        raise ValidationError("Password must be text", "bad_password")
    if len(password) < config.MIN_PASSWORD_LEN:
        raise ValidationError(
            f"Password must be at least {config.MIN_PASSWORD_LEN} characters", "weak_password")
    if len(password) > config.MAX_PASSWORD_LEN:
        raise ValidationError(
            f"Password must be at most {config.MAX_PASSWORD_LEN} characters", "bad_password")
    if password.strip() == "":
        raise ValidationError("Password cannot be only spaces", "weak_password")
    return password


def validate_message_text(text: Any, max_chars: int | None = None) -> str:
    limit = max_chars or config.MAX_MESSAGE_CHARS
    if not isinstance(text, str):
        raise ValidationError("Message must be text", "bad_message")
    if "\x00" in text:
        raise ValidationError("Message contains a null byte", "bad_message")
    cleaned = CONTROL_RE.sub("", text).strip()
    if not cleaned:
        raise ValidationError("Message cannot be empty", "empty_message")
    if len(cleaned) > limit:
        raise ValidationError(f"Message exceeds {limit} characters", "message_too_long")
    return cleaned


def validate_user_id(value: Any, field: str = "receiver_id") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        else:
            raise ValidationError(f"{field} must be an integer", "bad_id")
    if value <= 0:
        raise ValidationError(f"{field} must be positive", "bad_id")
    return int(value)


def validate_group_id(value: Any) -> int:
    return validate_user_id(value, "group_id")


def validate_group_name(name: Any) -> str:
    if not isinstance(name, str):
        raise ValidationError("Group name must be text", "bad_group_name")
    cleaned = CONTROL_RE.sub("", name).strip()
    if not cleaned:
        raise ValidationError("Group name cannot be empty", "bad_group_name")
    if len(cleaned) > config.MAX_GROUP_NAME_LEN:
        raise ValidationError(
            f"Group name exceeds {config.MAX_GROUP_NAME_LEN} characters", "bad_group_name")
    return cleaned


def validate_int(value: Any, field: str, minimum: int = 0, maximum: int = 10_000) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be an integer", "bad_value")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be an integer", "bad_value") from exc
    if not (minimum <= number <= maximum):
        raise ValidationError(f"{field} must be between {minimum} and {maximum}", "bad_value")
    return number


def validate_token(token: Any) -> str:
    if not isinstance(token, str) or not token:
        raise ValidationError("Missing session token", "missing_token")
    if len(token) > 256:
        raise ValidationError("Session token is malformed", "bad_token")
    return token


def validate_ip(value: Any) -> str:
    """Best-effort normalisation; never trusted for authorisation."""
    if not isinstance(value, str):
        return "unknown"
    return value[:64]


# ── output hygiene ────────────────────────────────────────────────────────
def sanitize_for_log(text: Any, limit: int = 120) -> str:
    """Strip control characters and truncate before anything reaches a log file.

    Stops a client from forging fake log lines with \\n, and keeps a 4000
    character message from filling the disk.
    """
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    s = CONTROL_RE.sub("", s).replace("\n", " ").replace("\t", " ")
    return s[:limit]


SENSITIVE_KEYS = {"password", "token", "session_token", "secret", "password_hash"}


def redact(payload: dict) -> dict:
    """Copy of a payload with secrets replaced, for safe logging."""
    if not isinstance(payload, dict):
        return {"_": sanitize_for_log(payload)}
    out = {}
    for key, value in payload.items():
        if key.lower() in SENSITIVE_KEYS:
            out[key] = "***redacted***"
        elif isinstance(value, dict):
            out[key] = redact(value)
        else:
            out[key] = value
    return out


def validate_message_type(msg_type: str, allowed: Iterable[str]) -> str:
    if msg_type not in allowed:
        raise ValidationError(f"Unsupported message type: {msg_type}", "unknown_type")
    return msg_type
