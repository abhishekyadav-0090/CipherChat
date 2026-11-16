"""Length-prefixed framing for the TCP transport.

A TCP stream has no message boundaries: one ``recv()`` may return half a JSON
object, or three of them glued together. So every frame is sent as

    [ 4-byte big-endian length ][ UTF-8 JSON bytes ]

and the reader buffers until it has a complete frame. This is the single most
common place a hand-written chat server breaks, and the reason the frontend
must use this exact framing rather than sending bare JSON.

WebSocket does not need this: frames already have boundaries.
"""
from __future__ import annotations

import json
import struct
from typing import Any

import config

HEADER = struct.Struct("!I")   # network byte order, unsigned 32-bit


class FrameError(Exception):
    pass


def encode_frame(payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(body) > config.MAX_FRAME_BYTES:
        raise FrameError(f"Frame too large ({len(body)} bytes)")
    return HEADER.pack(len(body)) + body


def encode_text(text: str) -> bytes:
    body = text.encode("utf-8")
    return HEADER.pack(len(body)) + body


class FrameReader:
    """Feed it bytes, get whole payloads back."""

    def __init__(self, max_frame: int = config.MAX_FRAME_BYTES) -> None:
        self.max_frame = max_frame
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        self._buffer.extend(chunk)
        out: list[bytes] = []
        while True:
            if len(self._buffer) < HEADER.size:
                break
            (length,) = HEADER.unpack_from(self._buffer, 0)
            if length == 0:
                # Zero-length frames are a protocol violation, not a keepalive.
                raise FrameError("Zero-length frame")
            if length > self.max_frame:
                raise FrameError(f"Declared frame size {length} exceeds limit {self.max_frame}")
            if len(self._buffer) < HEADER.size + length:
                break
            start = HEADER.size
            out.append(bytes(self._buffer[start:start + length]))
            del self._buffer[:start + length]
        return out

    @property
    def pending(self) -> int:
        return len(self._buffer)


def decode_json(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8"))
