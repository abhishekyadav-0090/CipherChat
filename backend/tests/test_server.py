"""End-to-end server tests over real sockets.

These start the actual ChatServer on an ephemeral port and talk to it with the
reference client, so they cover the parts unit tests cannot: TLS handshake,
length-prefixed framing, thread-per-client, and clean shutdown.

TLS is used when certificates exist; otherwise the same tests run in plaintext.
"""
from __future__ import annotations

import socket
import threading
import time
import unittest
from pathlib import Path

import config
from server.server import ChatServer
from tools.client_lib import CipherChatClient

CERTS_AVAILABLE = Path(config.CERT_FILE).exists() and Path(config.KEY_FILE).exists()


class ServerTestCase(unittest.TestCase):
    use_tls = True
    enable_wss = False

    @classmethod
    def setUpClass(cls):
        if cls.use_tls and not CERTS_AVAILABLE:
            raise unittest.SkipTest("certificates missing — run tools/gen_certs.py")

    def setUp(self) -> None:
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.server = ChatServer(
            host="127.0.0.1", port=0, use_tls=self.use_tls,
            db_path=str(Path(self.tmp.name) / "server.db"),
            enable_wss=self.enable_wss,
        )
        self.server.start()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.2)
        self.clients: list[CipherChatClient] = []

    def tearDown(self) -> None:
        for client in self.clients:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.tmp.cleanup()

    def connect(self) -> CipherChatClient:
        client = CipherChatClient(host="127.0.0.1", port=self.server.port,
                                  ca_file=config.CA_FILE, use_tls=self.use_tls)
        client.connect()
        self.clients.append(client)
        return client

    def new_user(self, name: str) -> CipherChatClient:
        client = self.connect()
        client.register(name, "TestPass123")
        response = client.login(name, "TestPass123")
        self.assertTrue(response.get("success"), response)
        client.drain()
        return client


class TLSIntegrationTests(ServerTestCase):
    use_tls = True

    def test_tls_handshake_and_version(self):
        client = self.connect()
        info = client.info()
        self.assertTrue(info["tls"])
        self.assertIn(info["version"], ("TLSv1.2", "TLSv1.3"))

    def test_register_login_over_tls(self):
        client = self.connect()
        response = client.register("SocketUser", "TestPass123")
        self.assertTrue(response["success"])
        self.assertEqual(response.get("username"), "SocketUser")

        login = client.login("SocketUser", "TestPass123")
        self.assertTrue(login["success"])
        self.assertIsNotNone(login["session_token"])

    def test_two_clients_exchange_a_message(self):
        alice = self.new_user("NetAlice")
        bob = self.new_user("NetBob")

        response = alice.send_message(bob.user_id, "hello over TLS")
        self.assertEqual(response["type"], "message_response")
        self.assertEqual(response["status"], "delivered")

        incoming = bob.wait_for({"incoming_message"}, timeout=5)
        self.assertEqual(incoming["message"], "hello over TLS")
        self.assertEqual(incoming["sender"], "NetAlice")

    def test_five_clients_connect_simultaneously(self):
        clients = [self.new_user(f"Multi{i}") for i in range(5)]
        self.assertEqual(len({c.user_id for c in clients}), 5)

        for i, client in enumerate(clients):
            target = clients[(i + 1) % 5]
            response = client.send_message(target.user_id, f"ping from {i}")
            self.assertEqual(response["status"], "delivered")

        for i, client in enumerate(clients):
            message = client.wait_for({"incoming_message"}, timeout=5)
            self.assertIn("ping from", message["message"])

    def test_server_rejects_unauthenticated_actions(self):
        client = self.connect()
        response = client.request({"type": "get_users"}, ("users_response", "error"))
        self.assertEqual(response["code"], "not_authenticated")

    def test_malformed_frame_gets_an_error_not_a_crash(self):
        client = self.connect()
        client.send_text_frame("{this is not json}")
        error = client.wait_for({"error"}, timeout=5)
        self.assertEqual(error["code"], "malformed_json")

        # The connection must still work afterwards.
        response = client.request({"type": "ping"}, "pong")
        self.assertEqual(response["type"], "pong")

    def test_unverified_client_is_also_served_but_that_is_the_point(self):
        """Documents the difference: verification is the client's job."""
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw = socket.create_connection(("127.0.0.1", self.server.port), timeout=5)
        tls = ctx.wrap_socket(raw, server_hostname="localhost")
        self.assertIsNotNone(tls.version())
        tls.close()

    def test_presence_updates_when_a_client_disconnects(self):
        alice = self.new_user("PresenceAlice")
        bob = self.new_user("PresenceBob")
        bob.close()
        time.sleep(0.4)

        alice.drain()
        alice.send({"type": "get_users"})
        response = alice.wait_for({"users_response"}, timeout=5)
        statuses = {u["username"]: u["status"] for u in response["users"]}
        self.assertEqual(statuses["PresenceBob"], "offline")

    def test_graceful_shutdown_notifies_clients(self):
        client = self.new_user("ShutdownUser")
        self.server.shutdown()
        message = client.wait_for({"server_shutdown", "_disconnected"}, timeout=5)
        self.assertIn(message["type"], ("server_shutdown", "_disconnected"))
        # tearDown will call shutdown again; it must be idempotent.
        self.server.shutdown()


class WebSocketTests(ServerTestCase):
    """The wss:// bridge must speak the same protocol as the TCP server."""
    use_tls = True
    enable_wss = True

    def _ws_connect(self):
        try:
            from websockets.asyncio.client import connect
        except Exception:  # noqa: BLE001
            self.skipTest("websockets package not installed")
        from security.tls_config import build_client_context
        return connect(f"wss://localhost:{self.server._ws.port}",
                       ssl=build_client_context(config.CA_FILE), max_size=65536)

    def test_register_login_and_ping_over_wss(self):
        import asyncio, json

        async def scenario():
            async with self._ws_connect() as ws:
                async def call(payload, want):
                    await ws.send(json.dumps(payload))
                    for _ in range(10):
                        message = json.loads(await asyncio.wait_for(ws.recv(), 5))
                        if message.get("type") == want:
                            return message
                    raise AssertionError(f"no {want}")

                register = await call({"type": "register", "username": "wsuser",
                                       "password": "WsPass1234"}, "register_response")
                self.assertTrue(register["success"])
                login = await call({"type": "login", "username": "wsuser",
                                    "password": "WsPass1234"}, "login_response")
                self.assertTrue(login["success"])
                pong = await call({"type": "ping"}, "pong")
                self.assertIn("server_time", pong)
                error = await call({"type": "not_a_type"}, "error")
                self.assertEqual(error["code"], "unknown_type")

        asyncio.run(scenario())


class PlaintextIntegrationTests(ServerTestCase):
    """Same server with TLS off — this is the mode used for the Wireshark demo."""
    use_tls = False

    def test_plaintext_still_routes_messages(self):
        alice = self.new_user("PlainAlice")
        bob = self.new_user("PlainBob")
        response = alice.send_message(bob.user_id, "unencrypted hello")
        self.assertEqual(response["status"], "delivered")
        self.assertEqual(bob.wait_for({"incoming_message"}, timeout=5)["message"],
                         "unencrypted hello")

    def test_client_reports_no_tls(self):
        client = self.connect()
        self.assertFalse(client.info()["tls"])


if __name__ == "__main__":
    unittest.main()
