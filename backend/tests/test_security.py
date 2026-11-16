"""Security tests: validation, framing, redaction, TLS configuration."""
from __future__ import annotations

import ssl
import unittest
from pathlib import Path

from tests.helpers import EngineTestCase
import config
from security.input_validation import (
    ValidationError, parse_frame, redact, sanitize_for_log, validate_message_text,
    validate_password, validate_username,
)
from server.framing import FrameError, FrameReader, encode_frame


class ValidationTests(unittest.TestCase):
    def test_good_username(self):
        self.assertEqual(validate_username(" Abhishek_1 "), "Abhishek_1")

    def test_bad_usernames(self):
        for bad in ("ab", "", "x" * 30, "1abc", "has space", "semi;colon", "admin"):
            with self.assertRaises(ValidationError, msg=f"accepted {bad!r}"):
                validate_username(bad)

    def test_password_bounds(self):
        self.assertEqual(validate_password("goodpass1"), "goodpass1")
        for bad in ("short", "x" * 200, "        "):
            with self.assertRaises(ValidationError, msg=f"accepted {bad!r}"):
                validate_password(bad)

    def test_message_cleaning(self):
        self.assertEqual(validate_message_text("  hi  "), "hi")
        self.assertEqual(validate_message_text("a\x01b"), "ab")
        self.assertEqual(validate_message_text("line1\nline2"), "line1\nline2")

    def test_message_rejections(self):
        for bad in ("", "   ", "x" * (config.MAX_MESSAGE_CHARS + 1), "bad\x00null"):
            with self.assertRaises(ValidationError, msg=f"accepted {bad[:20]!r}"):
                validate_message_text(bad)

    def test_non_string_message_rejected(self):
        with self.assertRaises(ValidationError):
            validate_message_text({"not": "text"})


class FrameTests(unittest.TestCase):
    def test_roundtrip(self):
        payload = {"type": "ping", "n": 1}
        reader = FrameReader()
        frames = reader.feed(encode_frame(payload))
        self.assertEqual(len(frames), 1)
        self.assertEqual(parse_frame(frames[0]), payload)

    def test_partial_frames_are_buffered(self):
        data = encode_frame({"type": "ping"})
        reader = FrameReader()
        self.assertEqual(reader.feed(data[:3]), [])       # header incomplete
        self.assertEqual(reader.feed(data[3:7]), [])      # body incomplete
        frames = reader.feed(data[7:])
        self.assertEqual(len(frames), 1)

    def test_multiple_frames_in_one_read(self):
        reader = FrameReader()
        frames = reader.feed(encode_frame({"type": "a"}) + encode_frame({"type": "b"}))
        self.assertEqual([parse_frame(f)["type"] for f in frames], ["a", "b"])

    def test_oversized_declaration_is_refused_before_allocating(self):
        import struct
        reader = FrameReader(max_frame=100)
        with self.assertRaises(FrameError):
            reader.feed(struct.pack("!I", 10_000_000))

    def test_zero_length_frame_refused(self):
        import struct
        reader = FrameReader()
        with self.assertRaises(FrameError):
            reader.feed(struct.pack("!I", 0))

    def test_malformed_json(self):
        with self.assertRaises(ValidationError) as ctx:
            parse_frame(b"{not json}")
        self.assertEqual(ctx.exception.code, "malformed_json")

    def test_non_object_json(self):
        with self.assertRaises(ValidationError):
            parse_frame(b"[1,2,3]")

    def test_missing_type(self):
        with self.assertRaises(ValidationError) as ctx:
            parse_frame(b'{"username":"x"}')
        self.assertEqual(ctx.exception.code, "missing_type")

    def test_bad_utf8(self):
        with self.assertRaises(ValidationError):
            parse_frame(b"\xff\xfe\x00")


class RedactionTests(unittest.TestCase):
    def test_passwords_are_redacted(self):
        cleaned = redact({"type": "login", "username": "a", "password": "hunter2"})
        self.assertEqual(cleaned["password"], "***redacted***")
        self.assertEqual(cleaned["username"], "a")

    def test_tokens_are_redacted(self):
        cleaned = redact({"session_token": "abc123", "nested": {"token": "xyz"}})
        self.assertEqual(cleaned["session_token"], "***redacted***")
        self.assertEqual(cleaned["nested"]["token"], "***redacted***")

    def test_log_sanitiser_strips_newlines(self):
        self.assertEqual(sanitize_for_log("line1\nFAKE LOG ENTRY"), "line1 FAKE LOG ENTRY")

    def test_log_sanitiser_truncates(self):
        self.assertLessEqual(len(sanitize_for_log("x" * 500, limit=50)), 50)


class TLSTests(unittest.TestCase):
    def test_server_context_requires_a_certificate(self):
        from security.tls_config import TLSConfigError, build_server_context
        with self.assertRaises(TLSConfigError):
            build_server_context("/nonexistent/server.crt", "/nonexistent/server.key")

    def test_client_context_verifies_by_default(self):
        from security.tls_config import build_client_context
        ctx = build_client_context(config.CA_FILE)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    def test_generated_contexts_when_certs_exist(self):
        from security.tls_config import build_client_context, build_server_context
        if not Path(config.CERT_FILE).exists():
            self.skipTest("certificates not generated (run tools/gen_certs.py)")
        server_ctx = build_server_context()
        self.assertEqual(server_ctx.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertTrue(server_ctx.options & ssl.OP_NO_COMPRESSION)
        client_ctx = build_client_context(config.CA_FILE)
        self.assertEqual(client_ctx.verify_mode, ssl.CERT_REQUIRED)


class MonitorTests(EngineTestCase):
    def test_security_events_are_counted(self):
        self.monitor.login_failed("someone", "1.2.3.4", "bad password")
        self.monitor.impersonation_attempt("bob", "alice", "1.2.3.4")
        counters = self.monitor.snapshot()["counters"]
        self.assertEqual(counters["login_failed"], 1)
        self.assertEqual(counters["impersonation_attempt"], 1)

    def test_suspicious_requests_are_counted_from_the_engine(self):
        conn = self.make_user("Tester")
        self.engine.handle(conn, {"type": "not_a_real_type"})
        self.assertEqual(conn.last("error")["code"], "unknown_type")
        self.assertGreater(self.monitor.snapshot()["counters"]
                           .get("suspicious_request", 0), 0)


if __name__ == "__main__":
    unittest.main()
