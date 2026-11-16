#!/usr/bin/env python3
"""Interactive reference client — the frontend contract in executable form.

    python tools/cli_client.py --host 192.168.1.10
    python tools/cli_client.py --plain          # matches `python main.py --plain`

Commands:
    /register <user> <password>
    /login <user> <password>
    /users
    /msg <username> <text>
    /history <username> [limit]
    /group <name>                     create a group
    /groups
    /gmsg <group_id> <text>
    /typing <username>
    /ping
    /info                             show TLS version and cipher
    /quit
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from tools.client_lib import CipherChatClient

HELP = __doc__


def print_incoming(client: CipherChatClient) -> None:
    """Background printer so incoming messages appear while you are typing."""
    while True:
        try:
            message = client.inbox.get(timeout=0.5)
        except Exception:  # noqa: BLE001 - queue.Empty
            if client.sock is None:
                return
            continue
        kind = message.get("type")
        if kind == "_disconnected":
            print("\n[!] disconnected from server")
            return
        if kind == "incoming_message":
            print(f"\n  << {message['sender']}: {message['message']}")
        elif kind == "incoming_group_message":
            print(f"\n  << [{message.get('group_name')}] {message['sender']}: "
                  f"{message['message']}")
        elif kind == "presence":
            names = ", ".join(u["username"] for u in message.get("online", []))
            print(f"\n  ~~ online: {names or '(nobody)'}")
        elif kind == "typing":
            print(f"\n  ~~ {message['sender']} is typing...")
        elif kind == "delivery_ack":
            print(f"\n  ~~ message {message['message_id']} delivered")
        elif kind == "read_receipt":
            print(f"\n  ~~ message {message['message_id']} read")
        elif kind == "server_shutdown":
            print("\n[!] server is shutting down")
            return
        else:
            print(f"\n  << {kind}: {message}")


def resolve_username(client: CipherChatClient, username: str) -> int | None:
    users = client.request({"type": "get_users"}, "users_response").get("users", [])
    for user in users:
        if user["username"].lower() == username.lower():
            return user["user_id"]
    print(f"[!] no such user: {username}")
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CipherChat reference client")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--ca", default=str(config.CA_FILE), help="CA certificate to verify")
    parser.add_argument("--plain", action="store_true", help="connect without TLS")
    args = parser.parse_args(argv)

    client = CipherChatClient(host=args.host, port=args.port, ca_file=args.ca,
                              use_tls=not args.plain)
    try:
        client.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"[!] could not connect to {args.host}:{args.port} — {exc}")
        print("    Is the server running? Is the port right? Is TLS on both ends?")
        return 2

    info = client.info()
    if info.get("tls"):
        print(f"[+] connected with {info['version']} / {info['cipher']}")
    else:
        print("[+] connected WITHOUT TLS (demo mode)")
    print("type /help for commands\n")

    threading.Thread(target=print_incoming, args=(client,), daemon=True).start()

    try:
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if not line.startswith("/"):
                print("commands start with / — try /help")
                continue

            parts = line.split(maxsplit=2)
            command = parts[0].lower()
            try:
                if command in ("/quit", "/exit"):
                    break
                elif command == "/help":
                    print(HELP)
                elif command == "/register":
                    response = client.register(parts[1], parts[2])
                    print(f"  {response.get('message')}")
                elif command == "/login":
                    response = client.login(parts[1], parts[2])
                    print(f"  {response.get('message')}")
                elif command == "/users":
                    response = client.request({"type": "get_users"}, "users_response")
                    for user in response.get("users", []):
                        mark = "*" if user["status"] == "online" else " "
                        print(f"   {mark} {user['username']:<20} {user['status']}")
                elif command == "/msg":
                    receiver_id = resolve_username(client, parts[1])
                    if receiver_id:
                        response = client.send_message(receiver_id, parts[2])
                        if response.get("type") == "error":
                            print(f"  [!] {response['code']}: {response['message']}")
                        else:
                            print(f"  sent (id {response['message_id']}, {response['status']})")
                elif command == "/history":
                    receiver_id = resolve_username(client, parts[1])
                    if receiver_id:
                        limit = int(parts[2]) if len(parts) > 2 else 20
                        response = client.request(
                            {"type": "message_history", "with_user_id": receiver_id,
                             "limit": limit}, "history_response")
                        for m in response.get("messages", []):
                            print(f"   [{m['timestamp'][11:19]}] {m['sender']}: {m['message']}")
                elif command == "/group":
                    response = client.request({"type": "create_group", "name": parts[1]},
                                              "group_response")
                    print(f"  group {response['group_id']} created: {response['name']}")
                elif command == "/groups":
                    response = client.request({"type": "get_groups"}, "groups_response")
                    for g in response.get("groups", []):
                        print(f"   {g['group_id']}: {g['name']} ({', '.join(g['members'])})")
                elif command == "/gmsg":
                    response = client.request(
                        {"type": "group_message", "group_id": int(parts[1]),
                         "message": parts[2]}, ("message_response", "error"))
                    print(f"  {response.get('status', response.get('message'))}")
                elif command == "/typing":
                    receiver_id = resolve_username(client, parts[1])
                    if receiver_id:
                        client.send({"type": "typing", "receiver_id": receiver_id})
                elif command == "/ping":
                    response = client.request({"type": "ping"}, "pong")
                    print(f"  pong at {response['server_time']}")
                elif command == "/info":
                    response = client.request({"type": "server_info"}, "server_info_response")
                    print(f"   transport={response['transport']} tls={response['tls']} "
                          f"stats={response['stats']}")
                else:
                    print("unknown command — /help")
            except IndexError:
                print("missing arguments — /help")
            except TimeoutError:
                print("[!] no response (server busy or disconnected)")
            except ConnectionError as exc:
                print(f"[!] {exc}")
                break
    finally:
        client.close()
        print("bye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
