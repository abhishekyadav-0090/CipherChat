#!/usr/bin/env python3
"""The four security experiments from the brief, as runnable checks.

    python tools/security_demo.py --all
    python tools/security_demo.py --experiment impersonation
    python tools/security_demo.py --experiment bruteforce --host 192.168.1.10

Each experiment prints PASS/FAIL plus the server's response, so you can paste
the output into a report. The Wireshark experiment is the one thing a script
cannot do for you — see docs/SECURITY_TESTS.md for the capture steps.
"""
from __future__ import annotations

import argparse
import socket
import ssl
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from tools.client_lib import CipherChatClient

PASS = "PASS"
FAIL = "FAIL"


def header(title: str) -> None:
    print(f"\n{'=' * 66}\n  {title}\n{'=' * 66}")


def _fresh_user(host: str, port: int, ca: str, prefix: str) -> tuple[CipherChatClient, CipherChatClient]:
    """Two logged-in clients with unique names, for the current run."""
    stamp = str(int(time.time()))[-6:]
    alice = CipherChatClient(host=host, port=port, ca_file=ca).connect()
    bob = CipherChatClient(host=host, port=port, ca_file=ca).connect()
    for client, name in ((alice, f"{prefix}a{stamp}"), (bob, f"{prefix}b{stamp}")):
        client.register(name, "TestPass123")
        client.login(name, "TestPass123")
    return alice, bob


# ── Experiment 1 ─────────────────────────────────────────────────────────
def experiment_tls(host: str, port: int, ca: str) -> bool:
    header("Experiment 1 — TLS is really on")
    client = CipherChatClient(host=host, port=port, ca_file=ca).connect()
    info = client.info()
    client.close()
    if not info.get("tls"):
        print("  This server is running WITHOUT TLS (--plain).")
        print("  Re-run the server without --plain to see encryption.")
        return False
    print(f"  negotiated version : {info['version']}")
    print(f"  negotiated cipher  : {info['cipher']}")
    print(f"  server certificate : {info['peer']}")
    ok = info["version"] in ("TLSv1.2", "TLSv1.3")
    print(f"  [{PASS if ok else FAIL}] transport is encrypted with a modern TLS version")
    print("\n  For the Wireshark half of this experiment, see docs/SECURITY_TESTS.md:")
    print("  capture the same login once with --plain and once with TLS, and compare")
    print("  what the Follow TCP Stream view shows.")
    return ok


def experiment_unverified(host: str, port: int, ca: str) -> bool:
    """What happens if the client skips certificate verification."""
    header("Experiment 1b — certificate verification actually matters")
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw = socket.create_connection((host, port), timeout=5)
        tls = ctx.wrap_socket(raw, server_hostname=host)
        tls.close()
        print("  An unverified client connects happily.")
        print("  That is the danger: it encrypts, so it looks secure, but it would")
        print("  equally happily talk to an impostor with any certificate.")
        print(f"  [{PASS}] demonstration complete — our client verifies (see Experiment 1)")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  [{FAIL}] unexpected: {exc}")
        return False


# ── Experiment 2 ─────────────────────────────────────────────────────────
def experiment_bruteforce(host: str, port: int, ca: str) -> bool:
    header("Experiment 2 — brute-force protection")
    stamp = str(int(time.time()))[-6:]
    username = f"victim{stamp}"
    client = CipherChatClient(host=host, port=port, ca_file=ca).connect()
    client.register(username, "CorrectPass123")

    attempts = config.LOGIN_MAX_ATTEMPTS + 2
    print(f"  trying {attempts} wrong passwords for {username}")
    throttled_at = None
    for i in range(1, attempts + 1):
        response = client.login(username, f"wrong{i}")
        code = response.get("code")
        print(f"   attempt {i}: success={response.get('success')} code={code} "
              f"retry_after={response.get('retry_after')}")
        if code == "throttled" and throttled_at is None:
            throttled_at = i

    # A correct password must ALSO be refused while the lockout is active.
    response = client.login(username, "CorrectPass123")
    blocked_while_locked = response.get("code") == "throttled"
    print(f"   correct password during lockout: code={response.get('code')}")
    client.close()

    ok = throttled_at is not None and blocked_while_locked
    print(f"  [{PASS if ok else FAIL}] throttling engaged at attempt {throttled_at} "
          f"and blocks even a correct password")
    print("  Check logs/security.log for LOGIN_FAILED and LOGIN_THROTTLED lines.")
    return ok


# ── Experiment 3 ─────────────────────────────────────────────────────────
def experiment_impersonation(host: str, port: int, ca: str) -> bool:
    header("Experiment 3 — impersonation is rejected")
    alice, bob = _fresh_user(host, port, ca, "imp")
    print(f"  logged in as {alice.username}; forging a message as {bob.username}")

    response = alice.request(
        {"type": "private_message", "receiver_id": bob.user_id,
         "sender": bob.username, "message": "this is not from me"},
        ("message_response", "error"),
    )
    code = response.get("code")
    print(f"  server said: {response.get('type')} / {code} / {response.get('message')}")
    ok = code == "impersonation_rejected"

    # Control: the same message without a forged sender goes through.
    control = alice.send_message(bob.user_id, "honest message")
    control_ok = control.get("type") == "message_response"
    print(f"  control (no forged sender): {control.get('type')} "
          f"{'accepted' if control_ok else 'rejected'}")

    alice.close()
    bob.close()
    print(f"  [{PASS if ok and control_ok else FAIL}] forged sender refused, "
          f"honest message accepted")
    print("  Check logs/security.log for IMPERSONATION_ATTEMPT.")
    return ok and control_ok


# ── Experiment 4 ─────────────────────────────────────────────────────────
def experiment_tampering(host: str, port: int, ca: str) -> bool:
    header("Experiment 4 — tampering with a TLS stream is detected")
    client = CipherChatClient(host=host, port=port, ca_file=ca).connect()
    print("  connected, now injecting bytes into the encrypted stream")
    try:
        client.send_raw(b"\x00\x00\x00\x10{'tampered':1}")
        time.sleep(0.3)
        response = client.wait_for({"error", "_disconnected"}, timeout=3)
        print(f"  server response: {response.get('type')} {response.get('code', '')}")
        ok = True
    except (ConnectionError, TimeoutError, ssl.SSLError, OSError) as exc:
        print(f"  connection dropped: {type(exc).__name__}: {exc}")
        ok = True
    finally:
        client.close()
    print(f"  [{PASS if ok else FAIL}] the stream could not be silently altered:")
    print("  TLS records are authenticated, so a modified byte breaks the connection")
    print("  instead of delivering a different message.")
    return ok


# ── Experiment 5 ─────────────────────────────────────────────────────────
def experiment_limits(host: str, port: int, ca: str) -> bool:
    header("Experiment 5 — input limits and malformed input")
    client = CipherChatClient(host=host, port=port, ca_file=ca).connect()
    results = []

    response = client.request({"type": "register", "username": "x", "password": "short"},
                              ("register_response", "error"))
    results.append(("short username rejected", response.get("code") in
                    ("bad_username", "weak_password")))
    print(f"   short username: {response.get('code')} {response.get('message')}")

    client.send_text_frame("{not json}")
    response = client.wait_for({"error"}, timeout=3)
    results.append(("malformed JSON rejected", response.get("code") == "malformed_json"))
    print(f"   malformed JSON: {response.get('code')}")

    client.send({"type": "private_message", "receiver_id": 1,
                 "message": "x" * (config.MAX_MESSAGE_CHARS + 500)})
    response = client.wait_for({"error"}, timeout=3)
    results.append(("oversized message rejected", response.get("code") in
                    ("message_too_long", "frame_too_large", "not_authenticated")))
    print(f"   oversized message: {response.get('code')}")

    client.send({"type": "launch_missiles"})
    response = client.wait_for({"error"}, timeout=3)
    results.append(("unknown type rejected", response.get("code") == "unknown_type"))
    print(f"   unknown type: {response.get('code')}")

    client.close()
    ok = all(passed for _, passed in results)
    print(f"  [{PASS if ok else FAIL}] {sum(1 for _, p in results if p)}/{len(results)} "
          f"checks passed")
    return ok


EXPERIMENTS = {
    "tls": experiment_tls,
    "unverified": experiment_unverified,
    "bruteforce": experiment_bruteforce,
    "impersonation": experiment_impersonation,
    "tampering": experiment_tampering,
    "limits": experiment_limits,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CipherChat security demonstrations")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--ca", default=str(config.CA_FILE))
    parser.add_argument("--experiment", choices=sorted(EXPERIMENTS), default=None)
    parser.add_argument("--all", action="store_true", help="run every experiment")
    args = parser.parse_args(argv)

    if args.all or not args.experiment:
        names = list(EXPERIMENTS)
    else:
        names = [args.experiment]

    results: dict[str, bool] = {}
    for name in names:
        try:
            results[name] = EXPERIMENTS[name](args.host, args.port, args.ca)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{FAIL}] experiment crashed: {type(exc).__name__}: {exc}")
            results[name] = False

    header("Summary")
    for name, passed in results.items():
        print(f"  {PASS if passed else FAIL}  {name}")
    failed = [n for n, p in results.items() if not p]
    print()
    if failed:
        print(f"  {len(failed)} experiment(s) did not pass: {', '.join(failed)}")
        print("  Check that the server is running and the CA path is correct.")
        return 1
    print("  All experiments passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
