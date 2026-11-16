"""Password hashing.

bcrypt is used when the package is installed (it is in requirements.txt).
If it is missing — a lab machine without pip access — the module falls back to
scrypt from the standard library, which is also a proper memory-hard KDF. What
it never falls back to is a bare SHA-256/MD5 digest, because those are not
password hashes: a GPU tries billions of them per second.

Stored format (the scheme prefix is what makes upgrades possible):

    bcrypt$<bcrypt-hash>
    scrypt$<n>$<r>$<p>$<salt-hex>$<hash-hex>

bcrypt silently truncates input at 72 bytes, so the password is pre-hashed
with SHA-256 and base64-encoded first. That is the standard fix and it keeps
long passphrases fully significant.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

try:  # pragma: no cover - depends on the machine
    import bcrypt as _bcrypt
except Exception:  # noqa: BLE001
    _bcrypt = None

BCRYPT_ROUNDS = 12
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def _prehash(password: str) -> bytes:
    """SHA-256 + base64 so bcrypt's 72-byte limit cannot truncate a passphrase."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")

    if _bcrypt is not None:
        salt = _bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        return "bcrypt$" + _bcrypt.hashpw(_prehash(password), salt).decode("ascii")

    salt = os.urandom(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time-ish verification. Returns False on any malformed input."""
    if not isinstance(password, str) or not isinstance(stored, str):
        return False

    try:
        scheme, _, rest = stored.partition("$")
        if scheme == "bcrypt" and _bcrypt is not None:
            return _bcrypt.checkpw(_prehash(password), rest.encode("ascii"))

        if scheme == "scrypt":
            n, r, p, salt_hex, hash_hex = rest.split("$")
            derived = hashlib.scrypt(
                password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2,
            )
            return hmac.compare_digest(derived.hex(), hash_hex)
    except Exception:  # noqa: BLE001 - malformed hash must never crash a login
        return False

    return False


def needs_rehash(stored: str) -> bool:
    """True when the hash was made with an older/weaker scheme than we use now."""
    if _bcrypt is not None:
        return not stored.startswith("bcrypt$")
    return not stored.startswith("scrypt$")


def random_token(nbytes: int = 32) -> str:
    """Cryptographically random session token. Not uuid4 — that is not secret."""
    return secrets.token_urlsafe(nbytes)
