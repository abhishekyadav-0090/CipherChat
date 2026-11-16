"""One thread per connected client.

Thread-per-client is the right trade for this project: simple to explain, simple
to debug, comfortable for the tens of clients a campus demo generates.

There is one subtlety worth understanding, because it is a real bug in a lot of
student TLS code. An ``ssl.SSLSocket`` must not be read and written at the same
time: OpenSSL keeps per-connection state, and concurrent SSL_read/SSL_write on
one object can deadlock or corrupt the stream. Since another client's thread may
push a message into this connection while this thread sits in ``recv()``, the
socket is made **non-blocking** and every SSL operation is serialised behind a
per-connection lock. ``select()`` waits outside the lock, so a blocked reader
never starves a writer.
"""
from __future__ import annotations

import select
import socket
import ssl
import threading
import time
from typing import Optional

import config
from monitoring.logger import app_log, log_error, log_event
from monitoring.security_monitor import SecurityMonitor
from security.input_validation import ValidationError, parse_frame, sanitize_for_log
from server.connection_manager import Connection, ConnectionManager
from server.framing import FrameError, FrameReader, encode_frame
from server.protocol_engine import ProtocolEngine

SELECT_INTERVAL = 0.25   # how long select() waits before the loop re-checks state


class TcpConnection(Connection):
    def __init__(self, sock: socket.socket, addr, transport: str = "tcp") -> None:
        super().__init__(addr, transport)
        self.sock = sock
        # Reentrant: a handler may send from inside the read lock.
        self.io_lock = threading.RLock()

    # ── sending ───────────────────────────────────────────────────────────
    def send_json(self, payload: dict) -> bool:
        if self.closed:
            return False
        try:
            data = encode_frame(payload)
        except FrameError as exc:
            app_log().error("Refusing to send oversized frame to %s: %s", self.describe(), exc)
            return False
        if not self._send_all(data):
            return False
        self.sent_frames += 1
        return True

    def _send_all(self, data: bytes) -> bool:
        view = memoryview(data)
        deadline = time.monotonic() + 10.0
        with self.io_lock:
            while view:
                try:
                    sent = self.sock.send(view)
                    if sent == 0:
                        self.closed = True
                        return False
                    view = view[sent:]
                except (ssl.SSLWantWriteError, ssl.SSLWantReadError):
                    # Non-blocking TLS wants to wait; let select decide.
                    if time.monotonic() > deadline:
                        self.closed = True
                        return False
                    try:
                        select.select([], [self.sock], [], 0.5)
                    except (OSError, ValueError):
                        self.closed = True
                        return False
                except (BrokenPipeError, ConnectionResetError, OSError):
                    self.closed = True
                    return False
        return True

    # ── receiving ─────────────────────────────────────────────────────────
    def recv_ready(self, timeout: float = SELECT_INTERVAL) -> bool:
        """Wait until readable. Called without the lock held."""
        try:
            ready, _, _ = select.select([self.sock], [], [], timeout)
            return bool(ready)
        except (OSError, ValueError):
            return False

    def read_chunk(self, size: int = config.RECV_CHUNK) -> Optional[bytes]:
        """Non-blocking read. Returns b'' on EOF, None if it would block."""
        with self.io_lock:
            try:
                return self.sock.recv(size)
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError, BlockingIOError):
                return None
            except (ConnectionResetError, OSError):
                return b""

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class ClientHandler(threading.Thread):
    def __init__(self, raw_sock: socket.socket, addr, engine: ProtocolEngine,
                 manager: ConnectionManager, monitor: SecurityMonitor,
                 tls_context: Optional[ssl.SSLContext], on_finish=None) -> None:
        super().__init__(daemon=True, name=f"client-{addr[0]}:{addr[1]}")
        self.raw_sock = raw_sock
        self.addr = addr
        self.engine = engine
        self.manager = manager
        self.monitor = monitor
        self.tls_context = tls_context
        self.on_finish = on_finish
        self.conn: Optional[TcpConnection] = None

    # ── thread body ───────────────────────────────────────────────────────
    def run(self) -> None:
        try:
            sock = self._handshake()
            if sock is None:
                return
            self._serve(sock)
        except Exception as exc:  # noqa: BLE001 - a bad client must not kill the server
            log_error("CLIENT_THREAD_CRASH", exc, detail=f"addr={self.addr}")
        finally:
            self._cleanup()

    def _handshake(self) -> Optional[socket.socket]:
        self.raw_sock.settimeout(15)
        if self.tls_context is None:
            log_event("CLIENT_CONNECTED", detail="plaintext transport", ip=self._ip())
            return self.raw_sock
        try:
            tls_sock = self.tls_context.wrap_socket(self.raw_sock, server_side=True)
        except ssl.SSLError as exc:
            self.monitor.suspicious_request("pre-handshake", self._ip(),
                                            f"TLS handshake failed: {exc.reason}")
            self._safe_close(self.raw_sock)
            return None
        except OSError:
            self._safe_close(self.raw_sock)
            return None
        log_event("CLIENT_CONNECTED",
                  detail=f"TLS {tls_sock.version()} {tls_sock.cipher()[0]}", ip=self._ip())
        return tls_sock

    def _serve(self, sock: socket.socket) -> None:
        transport = "tcp" if self.tls_context is not None else "tcp-plain"
        self.conn = TcpConnection(sock, self.addr, transport)
        if not self.manager.add(self.conn):
            self.conn.send_json({
                "type": "error", "code": "server_full",
                "message": "Server is at capacity, try again shortly",
            })
            return

        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        sock.setblocking(False)   # required for the lock/select pattern

        reader = FrameReader()
        last_activity = time.monotonic()

        while not self.conn.closed:
            if not self.conn.recv_ready():
                if time.monotonic() - last_activity > config.IDLE_TIMEOUT:
                    log_event("IDLE_TIMEOUT", detail=f"after {config.IDLE_TIMEOUT}s",
                              ip=self._ip())
                    self.conn.send_json({"type": "error", "code": "idle_timeout",
                                         "message": "Closing idle connection"})
                    break
                continue

            chunk = self.conn.read_chunk()
            if chunk is None:
                continue                      # would block; try again
            if chunk == b"":
                break                         # peer closed cleanly
            last_activity = time.monotonic()
            self.conn.received_frames += 1

            try:
                for raw in reader.feed(chunk):
                    self._dispatch(raw)
            except FrameError as exc:
                self.monitor.oversized_frame(self._ip(), reader.pending)
                self.conn.send_json({"type": "error", "code": "frame_error",
                                     "message": str(exc)})
                break

    def _dispatch(self, raw: bytes) -> None:
        assert self.conn is not None
        try:
            request = parse_frame(raw)
        except ValidationError as exc:
            self.monitor.malformed_frame(self._ip(), exc.code)
            self.conn.send_json({"type": "error", "code": exc.code, "message": exc.message})
            return
        except Exception as exc:  # noqa: BLE001
            self.monitor.malformed_frame(self._ip(), str(exc))
            return
        self.engine.handle(self.conn, request)

    # ── teardown ──────────────────────────────────────────────────────────
    def _cleanup(self) -> None:
        conn = self.conn
        if conn is None:
            self._safe_close(self.raw_sock)
            return

        was_authenticated = conn.authenticated
        username, user_id = conn.username, conn.user_id
        try:
            self.manager.remove(conn)
        except Exception:  # noqa: BLE001
            pass
        conn.close()

        if was_authenticated:
            log_event("CLIENT_DISCONNECTED",
                      detail=f"frames_in={conn.received_frames} frames_out={conn.sent_frames}",
                      ip=conn.ip, user=username)
            try:
                self.engine.announce_presence()
            except Exception:  # noqa: BLE001
                pass
            if user_id is not None and not self.manager.is_online(user_id):
                app_log().info("USER_OFFLINE %s", sanitize_for_log(username))
        else:
            log_event("CLIENT_DISCONNECTED", detail="was not authenticated", ip=conn.ip)

        if self.on_finish is not None:
            try:
                self.on_finish(self)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _safe_close(sock: socket.socket) -> None:
        try:
            sock.close()
        except OSError:
            pass

    def _ip(self) -> str:
        if isinstance(self.addr, tuple) and self.addr:
            return str(self.addr[0])
        return str(self.addr)
