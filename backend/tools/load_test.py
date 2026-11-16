#!/usr/bin/env python3
"""Multi-client test: the "five clients at once" deliverable, measured.

    python tools/load_test.py                      # 5 clients, 5 rounds
    python tools/load_test.py --clients 10 --rounds 20

Each client registers (or logs in if it already exists), then every client
sends one message to the next one in a ring. The script reports how many
messages were routed, how many were delivered to a live socket, and the
end-to-end latency of the last round. Run it against a live server.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from tools.client_lib import CipherChatClient


def make_client(host: str, port: int, ca: str, index: int,
                password: str) -> CipherChatClient | None:
    username = f"loaduser{index}"
    client = CipherChatClient(host=host, port=port, ca_file=ca)
    try:
        client.connect()
        response = client.register(username, password)
        if not response.get("success"):
            response = client.login(username, password)
            if not response.get("success"):
                print(f"[!] {username}: {response.get('message')}")
                client.close()
                return None
        else:
            client.login(username, password)
        return client
    except Exception as exc:  # noqa: BLE001
        print(f"[!] {username} failed: {exc}")
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CipherChat multi-client load test")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--ca", default=str(config.CA_FILE))
    parser.add_argument("--clients", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--password", default="loadtest123")
    args = parser.parse_args(argv)

    print(f"[*] connecting {args.clients} clients to {args.host}:{args.port}")
    clients: list[CipherChatClient] = []
    for i in range(args.clients):
        client = make_client(args.host, args.port, args.ca, i, args.password)
        if client is not None:
            clients.append(client)
        time.sleep(0.05)

    if len(clients) < 2:
        print("[!] need at least two clients to route messages")
        for client in clients:
            client.close()
        return 2

    print(f"[+] {len(clients)} clients authenticated: "
          f"{', '.join(c.username for c in clients)}")

    sent = delivered = failed = 0
    latencies: list[float] = []

    for round_no in range(1, args.rounds + 1):
        for i, client in enumerate(clients):
            target = clients[(i + 1) % len(clients)]
            started = time.perf_counter()
            response = client.send_message(target.user_id, f"round {round_no} from {client.username}")
            elapsed = (time.perf_counter() - started) * 1000
            if response.get("type") == "error":
                failed += 1
                print(f"  [!] {client.username}: {response['code']} {response['message']}")
                continue
            sent += 1
            latencies.append(elapsed)
            if response.get("status") == "delivered":
                delivered += 1

        time.sleep(0.2)

    # Every client should also have received what the previous one sent.
    time.sleep(0.5)
    received = sum(
        1 for client in clients
        for message in client.drain() if message.get("type") == "incoming_message"
    )

    print()
    print("  ── results ─────────────────────────────────────────")
    print(f"  clients connected     {len(clients)}")
    print(f"  messages sent         {sent}")
    print(f"  rejected              {failed}")
    print(f"  ack status delivered  {delivered}")
    print(f"  incoming received     {received} (queue drained after the run)")
    if latencies:
        print(f"  ack latency p50       {statistics.median(latencies):.1f} ms")
        print(f"  ack latency max       {max(latencies):.1f} ms")
    print("  ────────────────────────────────────────────────────")

    for client in clients:
        client.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
