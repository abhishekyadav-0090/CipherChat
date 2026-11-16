"""The listening socket and its lifecycle.

    socket() → setsockopt(SO_REUSEADDR) → bind(0.0.0.0, port) → listen()
    → loop: accept() → thread per client

Binding to 0.0.0.0 rather than 127.0.0.1 is what makes the server reachable
from phones and laptops on the same Wi-Fi. 127.0.0.1 only accepts connections
from the same machine, which is the classic reason a demo "works on my laptop"
and nowhere else.
"""
from __future__ import annotations

import socket
import ssl
import threading
import time
from typing import Optional

import config
from authentication.auth import AuthService
from authentication.session_manager import SessionManager
from database.database import Database
from messaging.message_handler import MessageHandler
from messaging.message_history import MessageHistory
from monitoring.logger import app_log, log_error, log_event
from monitoring.security_monitor import SecurityMonitor
from security.rate_limiter import RateLimiter
from server.client_handler import ClientHandler
from server.connection_manager import ConnectionManager
from server.message_router import MessageRouter
from server.protocol_engine import ProtocolEngine


class ChatServer:
    def __init__(self, host: str = config.HOST, port: int = config.PORT,
                 use_tls: bool = True, db_path: Optional[str] = None,
                 cert_file: Optional[str] = None, key_file: Optional[str] = None,
                 enable_wss: bool = config.ENABLE_WSS,
                 wss_port: int = config.WSS_PORT) -> None:
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.enable_wss = enable_wss
        self.wss_port = wss_port

        # ── build the object graph once, so every transport shares it ──────
        self.db = Database(db_path or config.DB_PATH)
        self.db.init_schema()
        self.sessions = SessionManager(self.db)
        self.limiter = RateLimiter()
        self.ip_limiter = RateLimiter(max_attempts=config.LOGIN_IP_MAX_ATTEMPTS)
        self.monitor = SecurityMonitor()
        self.auth = AuthService(self.db, self.sessions, self.limiter, self.monitor,
                                ip_limiter=self.ip_limiter)
        self.manager = ConnectionManager(max_clients=config.MAX_CLIENTS)
        self.handler = MessageHandler(self.db)
        self.history = MessageHistory(self.db)
        self.router = MessageRouter(self.manager, self.db)
        self.engine = ProtocolEngine(
            db=self.db, auth=self.auth, sessions=self.sessions, manager=self.manager,
            handler=self.handler, history=self.history, router=self.router,
            monitor=self.monitor,
        )

        self.tls_context: Optional[ssl.SSLContext] = None
        if use_tls:
            from security.tls_config import build_server_context
            self.tls_context = build_server_context(
                cert_file or config.CERT_FILE, key_file or config.KEY_FILE)

        self._socket: Optional[socket.socket] = None
        self._stop = threading.Event()
        self._threads: set[ClientHandler] = set()
        self._threads_lock = threading.Lock()
        self._ws = None
        self.started_at = time.time()

    # ── lifecycle ─────────────────────────────────────────────────────────
    def bind(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(config.LISTEN_BACKLOG)
        sock.settimeout(1.0)   # so the accept loop can notice a shutdown request
        self._socket = sock
        self.port = sock.getsockname()[1]   # resolves port 0 to the real port
        log_event("SERVER_STARTED",
                  detail=f"listening on {self.host}:{self.port} "
                         f"({'TLS' if self.use_tls else 'PLAINTEXT'})")

    def start(self) -> None:
        self.bind()
        if self.enable_wss:
            try:
                from server.ws_server import WsServer
                self._ws = WsServer(
                    engine=self.engine, manager=self.manager, monitor=self.monitor,
                    ssl_context=self.tls_context, host=self.host, port=self.wss_port,
                )
                self._ws.start()
                log_event("WSS_STARTED", detail=f"wss://{self.host}:{self.wss_port}")
            except Exception as exc:  # noqa: BLE001 - WS is optional
                log_error("WSS_START_FAILED", exc,
                          detail="continuing with the TCP server only")
                self._ws = None

    def serve_forever(self) -> None:
        assert self._socket is not None, "call start() before serve_forever()"
        while not self._stop.is_set():
            try:
                raw_sock, addr = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break  # socket closed during shutdown

            handler = ClientHandler(
                raw_sock=raw_sock, addr=addr, engine=self.engine,
                manager=self.manager, monitor=self.monitor,
                tls_context=self.tls_context, on_finish=self._thread_finished,
            )
            with self._threads_lock:
                self._threads.add(handler)
            handler.start()

        app_log().info("Accept loop stopped")

    def run(self) -> None:
        self.start()
        self.serve_forever()

    def shutdown(self) -> None:
        """Graceful: stop accepting, tell clients, close, join threads."""
        if self._stop.is_set():
            return
        self._stop.set()
        log_event("SERVER_SHUTDOWN", detail="graceful shutdown requested")

        try:
            if self._socket is not None:
                self._socket.close()
        except OSError:
            pass

        for conn in self.manager.all_connections():
            conn.send_json({"type": "server_shutdown",
                            "message": "Server is shutting down"})
        for conn in self.manager.all_connections():
            conn.close()

        if self._ws is not None:
            try:
                self._ws.stop()
            except Exception:  # noqa: BLE001
                pass

        deadline = time.time() + 3.0
        with self._threads_lock:
            threads = list(self._threads)
        for thread in threads:
            remaining = max(0.0, deadline - time.time())
            thread.join(timeout=remaining)

        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass
        app_log().info("Server stopped cleanly")

    # ── helpers ───────────────────────────────────────────────────────────
    def _thread_finished(self, handler: ClientHandler) -> None:
        with self._threads_lock:
            self._threads.discard(handler)

    def uptime(self) -> float:
        return time.time() - self.started_at

    def addresses(self) -> list[str]:
        """LAN addresses a phone can actually dial, for the startup banner."""
        addrs = set()
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                addrs.add(info[4][0])
        except OSError:
            pass
        try:  # does not send packets; just picks the outbound interface
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("8.8.8.8", 80))
            addrs.add(probe.getsockname()[0])
            probe.close()
        except OSError:
            pass
        addrs.discard("127.0.0.1")
        return sorted(addrs)
