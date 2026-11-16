"""Centralised logging: three streams, one setup call.

    app.log         everything the server does
    security.log    authentication failures, throttling, impersonation attempts
    connection.log  connect / disconnect / presence, the "connection logging"
                    deliverable from the brief

All three rotate, so a demo that runs for a week cannot fill the disk. A filter
redacts obvious secrets even if a caller forgets to — belt and braces, because
passwords in log files is the classic way this project loses marks.
"""
from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from pathlib import Path

import config

_CONFIGURED = False
_REDACTIONS = [
    (re.compile(r'("?(?:password|token|session_token|password_hash)"?\s*[:=]\s*)("[^"]*"|\'[^\']*\'|\S+)'),
     r"\1***redacted***"),
]


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        for pattern, replacement in _REDACTIONS:
            message = pattern.sub(replacement, message)
        record.msg = message
        record.args = ()
        return True


def _make_logger(name: str, filename: str, level: int) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(config.LOG_DIR) / filename

    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=config.LOG_MAX_BYTES, backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    file_handler.addFilter(RedactionFilter())
    logger.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                                           datefmt="%H:%M:%S"))
    console.addFilter(RedactionFilter())
    console.setLevel(logging.INFO)
    logger.addHandler(console)
    return logger


def setup_logging(level: str | None = None) -> None:
    """Idempotent: safe to call from main.py and from tests."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    lvl = getattr(logging, (level or config.LOG_LEVEL).upper(), logging.INFO)
    _make_logger("cipherchat", "app.log", lvl)
    _make_logger("cipherchat.security", "security.log", logging.INFO)
    _make_logger("cipherchat.connection", "connection.log", logging.INFO)
    _CONFIGURED = True


def get_logger(name: str = "cipherchat") -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def app_log() -> logging.Logger:
    return get_logger("cipherchat")


def security_log() -> logging.Logger:
    return get_logger("cipherchat.security")


def connection_log() -> logging.Logger:
    return get_logger("cipherchat.connection")


# ── convenience event helpers, so every module logs the same way ──────────
def log_event(event: str, detail: str = "", ip: str | None = None,
              user: str | None = None) -> None:
    parts = [f"{event:<22}"]
    if user:
        parts.append(f"user={user}")
    if ip:
        parts.append(f"ip={ip}")
    if detail:
        parts.append(detail)
    connection_log().info("  ".join(parts))


def log_security(event: str, detail: str = "", ip: str | None = None,
                 user: str | None = None) -> None:
    parts = [f"{event:<22}"]
    if user:
        parts.append(f"user={user}")
    if ip:
        parts.append(f"ip={ip}")
    if detail:
        parts.append(detail)
    security_log().warning("  ".join(parts))


def log_error(event: str, exc: BaseException | None = None, detail: str = "") -> None:
    message = f"{event:<22}  {detail}"
    if exc is not None:
        message += f"  error={type(exc).__name__}: {exc}"
    app_log().error(message)
