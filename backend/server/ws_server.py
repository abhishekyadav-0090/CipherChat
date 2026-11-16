"""Optional WebSocket front door (wss://) for a browser-based frontend.

Why this exists: a browser cannot open a raw TCP socket, so a React frontend
cannot talk to the TCP server directly. This bridge accepts WebSocket frames
and hands the decoded JSON to the *same* ProtocolEngine the TCP server uses —
one protocol, two carriers, no duplicated logic.

It is optional on purpose. If the `websockets` package is missing, the server
starts without it and says so, so the TCP path (the one the assignment is
really about) always works.
"""
from __future__ import annotations

import asyncio
import json
import ssl
import threading
from typing import Optional

import config
from monitoring.logger import app_log, log_error, log_event
from monitoring.security_monitor import SecurityMonitor
from security.input_validation import ValidationError, parse_frame, sanitize_for_log
from server.connection_manager import Connection, ConnectionManager
from server.protocol_engine import ProtocolEngine

try:  # pragma: no cover - optional dependency
    from websockets.asyncio.server import serve as ws_serve
    WEBSOCKETS_AVAILABLE = True
except Exception:  # noqa: BLE001
    ws_serve = None
    WEBSOCKETS_AVAILABLE = False


class WsConnection(Connection):
    """Adapts a websocket to the same interface the TCP connection exposes."""

    def __init__(self, ws, transport: str) -> None:
        super().__init__(getattr(ws, "remote_address", ("ws", 0)), transport)
        self.ws = ws
        self._queue: asyncio.Queue = asyncio.Queue()

    def send_json(self, payload: dict) -> bool:
        if self.closed:
            return False
        try:
            self._queue.put_nowait(payload)
            self.sent_frames += 1
            return True
        except Exception:  # noqa: BLE001
            self.closed = True
            return False

    async def writer(self) -> None:
        """Serialises sends so two handlers cannot interleave frames."""
        while not self.closed:
            payload = await self._queue.get()
            try:
                await self.ws.send(json.dumps(payload, separators=(",", ":")))
            except Exception:  # noqa: BLE001
                self.closed = True
                break

    def close(self) -> None:
        self.closed = True
        try:
            asyncio.get_running_loop().create_task(self.ws.close())
        except RuntimeError:
            pass


class WsServer:
    def __init__(self, engine: ProtocolEngine, manager: ConnectionManager,
                 monitor: SecurityMonitor, ssl_context: Optional[ssl.SSLContext],
                 host: str = config.HOST, port: int = config.WSS_PORT) -> None:
        self.engine = engine
        self.manager = manager
        self.monitor = monitor
        self.ssl_context = ssl_context
        self.host = host
        self.port = port
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self.error: Optional[BaseException] = None

    # ── lifecycle ─────────────────────────────────────────────────────────
    def start(self, wait: float = 3.0) -> None:
        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError("websockets package not installed (pip install websockets)")
        self._thread = threading.Thread(target=self._run, name="ws-bridge", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=wait)
        if self.error is not None:
            raise RuntimeError(f"WebSocket bridge failed: {self.error}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except BaseException as exc:  # noqa: BLE001
            self.error = exc
            log_error("WSS_CRASHED", exc)
        finally:
            self._ready.set()

    async def _main(self) -> None:
        transport = "wss" if self.ssl_context else "ws"
        async with ws_serve(
            self._handler, self.host, self.port,
            ssl=self.ssl_context,
            max_size=config.MAX_FRAME_BYTES,
            ping_interval=30, ping_timeout=30,
        ) as server:
            # Port 0 resolves to a real port here; tests rely on this.
            try:
                self.port = server.sockets[0].getsockname()[1]
            except Exception:  # noqa: BLE001
                pass
            self._ready.set()
            log_event("WSS_LISTENING", detail=f"{transport}://{self.host}:{self.port}")
            while not self._stop.is_set():
                await asyncio.sleep(0.2)

    # ── per connection ────────────────────────────────────────────────────
    async def _handler(self, ws) -> None:
        transport = "wss" if self.ssl_context else "ws"
        conn = WsConnection(ws, transport)
        if not self.manager.add(conn):
            await ws.close(code=1013, reason="server full")
            return

        writer_task = asyncio.create_task(conn.writer())
        log_event("CLIENT_CONNECTED", detail="websocket", ip=conn.ip)
        try:
            async for raw in ws:
                conn.received_frames += 1
                data = raw.encode("utf-8") if isinstance(raw, str) else raw
                if len(data) > config.MAX_FRAME_BYTES:
                    self.monitor.oversized_frame(conn.ip, len(data))
                    conn.send_json({"type": "error", "code": "frame_too_large",
                                    "message": "Message too large"})
                    break
                try:
                    request = parse_frame(data)
                except ValidationError as exc:
                    self.monitor.malformed_frame(conn.ip, exc.code)
                    conn.send_json({"type": "error", "code": exc.code,
                                    "message": exc.message})
                    continue
                # The engine is synchronous and fast (SQLite writes); running it
                # inline keeps ordering guarantees simple. A production build
                # would offload it with run_in_executor.
                self.engine.handle(conn, request)
        except Exception as exc:  # noqa: BLE001
            app_log().debug("WS connection ended: %s", exc)
        finally:
            was_authenticated = conn.authenticated
            username = conn.username
            self.manager.remove(conn)
            conn.closed = True
            writer_task.cancel()
            if was_authenticated:
                log_event("CLIENT_DISCONNECTED", detail="websocket",
                          ip=conn.ip, user=sanitize_for_log(username))
                try:
                    self.engine.announce_presence()
                except Exception:  # noqa: BLE001
                    pass
