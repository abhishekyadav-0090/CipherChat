#!/usr/bin/env python3
"""CipherChat backend entry point.

    python main.py                      # TLS on 0.0.0.0:5000 (+ wss on 5443)
    python main.py --plain              # no TLS, for the Wireshark comparison
    python main.py --port 6000 --no-ws  # TCP only, different port
    python main.py --host 127.0.0.1     # this machine only (no phone access)

Ctrl+C shuts down gracefully: clients are told, sockets closed, threads joined.
"""
from __future__ import annotations

import argparse
import signal
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from monitoring.logger import get_logger, setup_logging
from security.tls_config import TLSConfigError, build_server_context
from server.server import ChatServer

BANNER = r"""
   ___ _            _              ___ _
  / __(_)_ __  ___| |_  ___  ___ / __| |_  __ _ _ __
 | (__| | '_ \/ -_) ' \/ -_)|___| (__| ' \/ _` | '_ \
  \___|_| .__/\___|_||_\___|    \___|_||_\__,_| .__/
        |_|                                   |_|
"""


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CipherChat backend: TLS socket chat server with SQLite storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Default port 5000. Bind 0.0.0.0 so devices on your Wi-Fi can connect.",
    )
    parser.add_argument("--host", default=config.HOST, help="bind address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=config.PORT, help="TCP port (default 5000)")
    parser.add_argument("--wss-port", type=int, default=config.WSS_PORT,
                        help="WebSocket port for browser clients (default 5443)")
    parser.add_argument("--no-ws", action="store_true", help="disable the WebSocket bridge")
    parser.add_argument("--plain", action="store_true",
                        help="run WITHOUT TLS (only for the eavesdropping demonstration)")
    parser.add_argument("--cert", default=str(config.CERT_FILE), help="TLS certificate path")
    parser.add_argument("--key", default=str(config.KEY_FILE), help="TLS private key path")
    parser.add_argument("--db", default=str(config.DB_PATH), help="SQLite database path")
    parser.add_argument("--log-level", default=config.LOG_LEVEL, help="DEBUG/INFO/WARNING")
    return parser.parse_args(argv)


def print_banner(server: ChatServer, use_tls: bool, args) -> None:
    print(BANNER)
    print(f"  storage      {server.db.path}")
    print(f"  database     {server.db.count_users()} user(s), "
          f"{server.db.count_messages()} message(s)")
    print(f"  encryption   {'TLS enabled' if use_tls else 'PLAINTEXT (demo mode only)'}")
    print()
    print("  Frontend connects to:")
    print(f"    this machine     {'localhost' if use_tls else 'localhost'}:{args.port}"
          f"   {'TLS' if use_tls else 'no TLS'}")
    for addr in server.addresses():
        print(f"    on your Wi-Fi    {addr}:{args.port}")
    if args.host == "127.0.0.1":
        print("    (bound to 127.0.0.1 — other devices cannot connect)")
    print()
    if server._ws is not None:  # noqa: SLF001 - banner-only access
        for addr in server.addresses() or ["localhost"]:
            print(f"  browser client:    {'wss' if use_tls else 'ws'}://{addr}:{args.wss_port}")
        print()
    print("  Press Ctrl+C to stop.\n")


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_level)
    log = get_logger()

    use_tls = not args.plain
    if use_tls:
        try:
            build_server_context(args.cert, args.key)
        except TLSConfigError as exc:
            print(f"\n[!] {exc}\n")
            return 2
    else:
        log.warning("PLAINTEXT MODE — no transport encryption. "
                    "Use only for the eavesdropping demonstration.")

    try:
        server = ChatServer(
            host=args.host, port=args.port, use_tls=use_tls, db_path=args.db,
            cert_file=args.cert, key_file=args.key,
            enable_wss=not args.no_ws and use_tls, wss_port=args.wss_port,
        )
    except OSError as exc:
        print(f"\n[!] Cannot bind {args.host}:{args.port} — {exc}")
        print("    Is another copy of the server already running?\n")
        return 2

    print_banner(server, use_tls, args)

    def _shutdown(signum, frame):  # noqa: ARG001
        log.info("Signal %s received", signum)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
