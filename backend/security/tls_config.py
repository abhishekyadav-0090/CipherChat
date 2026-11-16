"""TLS setup for the server and for the reference client.

What this buys you, in one line: everything above the socket — passwords,
session tokens, message bodies — travels inside an encrypted, integrity-checked
tunnel, so a Wireshark capture of the same session shows TLS application data
instead of readable JSON.

Note the honest limit: TLS protects the wire. It is not end-to-end encryption —
the server can read message bodies because it has to store and route them.
E2EE would be the next project, not this one.
"""
from __future__ import annotations

import ssl
from pathlib import Path
from typing import Optional

import config


class TLSConfigError(Exception):
    pass


def build_server_context(cert_file: str | Path = config.CERT_FILE,
                         key_file: str | Path = config.KEY_FILE) -> ssl.SSLContext:
    cert_file, key_file = Path(cert_file), Path(key_file)
    if not cert_file.exists():
        raise TLSConfigError(
            f"Certificate not found: {cert_file}\n"
            f"Generate one with:  python tools/gen_certs.py"
        )
    if not key_file.exists():
        raise TLSConfigError(f"Private key not found: {key_file}")

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    # 1.3 is preferred automatically when both ends support it.
    ctx.options |= ssl.OP_NO_COMPRESSION          # CRIME
    ctx.options |= ssl.OP_CIPHER_SERVER_PREFERENCE
    if hasattr(ssl, "OP_NO_RENEGOTIATION"):
        ctx.options |= ssl.OP_NO_RENEGOTIATION
    try:
        ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:!aNULL:!MD5:!RC4:!3DES")
    except ssl.SSLError:
        pass
    ctx.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
    return ctx


def build_client_context(ca_file: Optional[str | Path] = None) -> ssl.SSLContext:
    """Client context that actually verifies the server.

    Verification is on and hostname checking is on. The alternative — an
    unverified context — is the single most common mistake in student TLS code:
    it encrypts, so it looks secure, but it happily talks to anyone.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    if ca_file is not None and Path(ca_file).exists():
        ctx.load_verify_locations(cafile=str(ca_file))
    else:
        ctx.load_default_certs()
    return ctx


def describe_context(ctx: ssl.SSLContext) -> dict:
    """Small dict for the startup banner and for the security demo output."""
    return {
        "min_version": ctx.minimum_version.name if hasattr(ctx, "minimum_version") else "?",
        "verify_mode": str(ctx.verify_mode),
        "check_hostname": getattr(ctx, "check_hostname", None),
    }


def peer_certificate_summary(sock: ssl.SSLSocket) -> dict:
    """What the client sees on the other end, for demo output."""
    try:
        cert = sock.getpeercert()
    except Exception:  # noqa: BLE001
        return {}
    if not cert:
        return {}
    subject = {k: v for item in cert.get("subject", ()) for k, v in item}
    issuer = {k: v for item in cert.get("issuer", ()) for k, v in item}
    return {
        "subject": subject.get("commonName", "?"),
        "issuer": issuer.get("commonName", "?"),
        "not_after": cert.get("notAfter"),
        "tls_version": sock.version(),
        "cipher": (sock.cipher() or ("?",))[0],
    }
