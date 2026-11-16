"""Small reusable TCP+TLS client used by the CLI client, the load test and the
security demos. Keeping one client means the demos cannot accidentally disagree
about framing or TLS settings.
"""
from __future__ import annotations

import json
import queue
import select
import socket
import ssl
import sys
import threading
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from security.tls_config import build_client_context
from server.framing import FrameReader, encode_frame, encode_text


class CipherChatClient:
    def __init__(self, host: str = "localhost", port: int = config.PORT,
                 ca_file: str | Path | None = config.CA_FILE,
                 use_tls: bool = True, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.timeout = timeout
        self.ca_file = ca_file
        self.sock: Optional[socket.socket] = None
        self.reader = FrameReader()
        self.inbox: "queue.Queue[dict]" = queue.Queue()
        self._closed = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        # One lock for all SSL operations on this socket: an SSLSocket must not
        # be read and written concurrently from two threads.
        self._io_lock = threading.RLock()
        self.session_token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.username: Optional[str] = None

    # ── connection ────────────────────────────────────────────────────────
    def connect(self) -> "CipherChatClient":
        raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.use_tls:
            ctx = build_client_context(self.ca_file)
            # SNI must match a SAN. When dialling a bare IP, localhost is not
            # right — so only send server_hostname when it is a hostname.
            try:
                self.sock = ctx.wrap_socket(raw, server_hostname=self.host)
            except ssl.SSLCertVerificationError:
                raw.close()
                raise
        else:
            self.sock = raw
        self.sock.settimeout(None)
        self.sock.setblocking(False)
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        return self

    def _read_loop(self) -> None:
        sock = self.sock
        if sock is None:
            return
        try:
            while not self._closed.is_set():
                try:
                    ready, _, _ = select.select([sock], [], [], 0.25)
                except (OSError, ValueError):
                    break
                if not ready:
                    continue
                with self._io_lock:
                    try:
                        chunk = sock.recv(config.RECV_CHUNK)
                    except (ssl.SSLWantReadError, ssl.SSLWantWriteError, BlockingIOError):
                        continue
                if not chunk:
                    break
                for raw in self.reader.feed(chunk):
                    try:
                        self.inbox.put(json.loads(raw.decode("utf-8")))
                    except Exception:  # noqa: BLE001
                        continue
        except (OSError, ssl.SSLError):
            pass
        finally:
            self._closed.set()
            self.inbox.put({"type": "_disconnected"})

    # ── sending ───────────────────────────────────────────────────────────
    def send(self, payload: dict) -> None:
        self.send_raw(encode_frame(payload))

    def send_raw(self, data: bytes) -> None:
        if self.sock is None or self._closed.is_set():
            raise ConnectionError("not connected")
        view = memoryview(data)
        deadline = time.monotonic() + self.timeout
        with self._io_lock:
            while view:
                try:
                    sent = self.sock.send(view)
                    view = view[sent:]
                except (ssl.SSLWantWriteError, ssl.SSLWantReadError, BlockingIOError):
                    if time.monotonic() > deadline:
                        raise TimeoutError("socket write timed out")
                    select.select([], [self.sock], [], 0.2)

    def send_text_frame(self, text: str) -> None:
        self.send_raw(encode_text(text))

    def request(self, payload: dict, expect: tuple[str, ...] | str,
                timeout: float = 5.0) -> dict:
        """Send one request and wait for the first matching response type."""
        expect_set = {expect} if isinstance(expect, str) else set(expect)
        # An error frame is always a valid answer: swallowing it would turn a
        # clear "username_taken" into a mysterious timeout.
        expect_set.add("error")
        self.send(payload)
        return self.wait_for(expect_set, timeout=timeout)

    def wait_for(self, types: set[str], timeout: float = 5.0) -> dict:
        """Wait for one of ``types``, without losing anything else.

        Frames that do not match are put back in the inbox in their original
        order. Without that, waiting for a message acknowledgement would quietly
        discard an incoming chat message that arrived at the same moment.
        """
        skipped: list[dict] = []
        deadline = time.monotonic() + timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"no response matching {types} within {timeout}s")
                try:
                    message = self.inbox.get(timeout=remaining)
                except queue.Empty:
                    raise TimeoutError(
                        f"no response matching {types} within {timeout}s") from None
                if message.get("type") in types:
                    return message
                if message.get("type") == "_disconnected":
                    raise ConnectionError("server closed the connection")
                skipped.append(message)
                if len(skipped) > 500:
                    raise RuntimeError("too many unrelated messages while waiting")
        finally:
            for message in reversed(skipped):
                self.inbox.queue.appendleft(message)

    def drain(self) -> list[dict]:
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    # ── convenience ───────────────────────────────────────────────────────
    def register(self, username: str, password: str) -> dict:
        return self.request({"type": "register", "username": username,
                             "password": password}, "register_response")

    def login(self, username: str, password: str) -> dict:
        response = self.request({"type": "login", "username": username,
                                 "password": password}, "login_response")
        if response.get("success"):
            self.session_token = response.get("session_token")
            self.user_id = response.get("user_id")
            self.username = response.get("username")
        return response

    def send_message(self, receiver_id: int, text: str) -> dict:
        return self.request({"type": "private_message", "receiver_id": receiver_id,
                             "message": text}, ("message_response", "error"))

    def info(self) -> dict:
        if isinstance(self.sock, ssl.SSLSocket):
            return {
                "tls": True,
                "version": self.sock.version(),
                "cipher": self.sock.cipher()[0],
                "peer": self.sock.getpeercert().get("subject"),
            }
        return {"tls": False}

    def close(self) -> None:
        self._closed.set()
        sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        # Let the reader thread notice the shutdown before we return, so it
        # cannot touch a closed socket during interpreter teardown.
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

    def __enter__(self) -> "CipherChatClient":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()
