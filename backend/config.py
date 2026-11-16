"""Central configuration for the CipherChat backend.

Every value can be overridden with an environment variable so the same code
runs on a laptop for the demo and on a VPS later without edits.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# ── Network ────────────────────────────────────────────────────────────────
# 0.0.0.0 (not 127.0.0.1) is what lets phones and laptops on the same Wi-Fi
# reach the server. 127.0.0.1 would only accept connections from this machine.
HOST = _env("CIPHERCHAT_HOST", "0.0.0.0")
PORT = _env_int("CIPHERCHAT_PORT", 5000)
WSS_PORT = _env_int("CIPHERCHAT_WSS_PORT", 5443)
ENABLE_WSS = _env("CIPHERCHAT_WSS", "1") not in ("0", "false", "no")

# ── Storage ────────────────────────────────────────────────────────────────
DATA_DIR = Path(_env("CIPHERCHAT_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = Path(_env("CIPHERCHAT_DB", str(DATA_DIR / "cipherchat.db")))
LOG_DIR = Path(_env("CIPHERCHAT_LOG_DIR", str(BASE_DIR / "logs")))

CERT_DIR = Path(_env("CIPHERCHAT_CERT_DIR", str(BASE_DIR / "certificates")))
CERT_FILE = Path(_env("CIPHERCHAT_CERT", str(CERT_DIR / "server.crt")))
KEY_FILE = Path(_env("CIPHERCHAT_KEY", str(CERT_DIR / "server.key")))
CA_FILE = Path(_env("CIPHERCHAT_CA", str(CERT_DIR / "ca.crt")))

# ── Protocol limits ────────────────────────────────────────────────────────
MAX_FRAME_BYTES = _env_int("CIPHERCHAT_MAX_FRAME", 64 * 1024)   # 64 KiB per JSON frame
MAX_MESSAGE_CHARS = _env_int("CIPHERCHAT_MAX_MESSAGE", 4000)     # one chat message
MAX_USERNAME_LEN = 24
MIN_USERNAME_LEN = 3
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128
MAX_GROUP_NAME_LEN = 48

# ── Connections ────────────────────────────────────────────────────────────
MAX_CLIENTS = _env_int("CIPHERCHAT_MAX_CLIENTS", 200)
IDLE_TIMEOUT = _env_int("CIPHERCHAT_IDLE_TIMEOUT", 300)   # seconds of silence before drop
LISTEN_BACKLOG = 64
RECV_CHUNK = 8192

# ── Sessions ───────────────────────────────────────────────────────────────
SESSION_TTL_SECONDS = _env_int("CIPHERCHAT_SESSION_TTL", 24 * 60 * 60)  # 24 h

# ── Login throttling ───────────────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS = _env_int("CIPHERCHAT_LOGIN_ATTEMPTS", 5)
# Per-IP limit is deliberately looser than the per-account limit: everyone in a
# hostel or on campus Wi-Fi shares one public IP, so a strict IP limit would let
# one attacker lock out every user behind the same NAT.
LOGIN_IP_MAX_ATTEMPTS = _env_int("CIPHERCHAT_LOGIN_IP_ATTEMPTS", 20)
LOGIN_WINDOW_SECONDS = _env_int("CIPHERCHAT_LOGIN_WINDOW", 15 * 60)   # 15 min window
LOGIN_LOCKOUT_SECONDS = _env_int("CIPHERCHAT_LOGIN_LOCKOUT", 15 * 60)

# ── TLS ────────────────────────────────────────────────────────────────────
TLS_MIN_VERSION = "TLSv1.2"   # 1.2 is the floor; 1.3 is negotiated when available

# ── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL = _env("CIPHERCHAT_LOG_LEVEL", "INFO")
LOG_MAX_BYTES = _env_int("CIPHERCHAT_LOG_MAX_BYTES", 5 * 1024 * 1024)
LOG_BACKUP_COUNT = _env_int("CIPHERCHAT_LOG_BACKUPS", 5)

# ── Reserved names ─────────────────────────────────────────────────────────
RESERVED_USERNAMES = {
    "admin", "root", "server", "system", "cipherchat", "support", "null", "none",
}
