"""Authentication tests: registration, login, hashing, sessions, throttling."""
from __future__ import annotations

import unittest

from tests.helpers import EngineTestCase
from authentication.password_manager import hash_password, verify_password
from security.rate_limiter import RateLimiter


class PasswordTests(unittest.TestCase):
    def test_hash_is_not_the_password(self):
        stored = hash_password("CorrectHorse123")
        self.assertNotIn("CorrectHorse123", stored)
        self.assertTrue(stored.startswith(("bcrypt$", "scrypt$")))

    def test_verify_accepts_correct_and_rejects_wrong(self):
        stored = hash_password("CorrectHorse123")
        self.assertTrue(verify_password("CorrectHorse123", stored))
        self.assertFalse(verify_password("correcthorse123", stored))
        self.assertFalse(verify_password("", stored))

    def test_two_hashes_of_same_password_differ(self):
        """Per-password salt: identical passwords must not produce identical hashes."""
        self.assertNotEqual(hash_password("same-password"), hash_password("same-password"))

    def test_long_passphrase_is_not_truncated(self):
        """bcrypt stops at 72 bytes; the pre-hash makes the tail significant."""
        base = "a" * 80
        stored = hash_password(base + "X")
        self.assertFalse(verify_password(base + "Y", stored))

    def test_malformed_hash_fails_closed(self):
        for bad in ("", "nonsense", "bcrypt$", "scrypt$1$2$3", "md5$abc"):
            self.assertFalse(verify_password("anything", bad))


class RegistrationTests(EngineTestCase):
    def test_register_then_login(self):
        conn = self.make_user("Abhishek")
        self.assertEqual(conn.username, "Abhishek")
        self.assertIsNotNone(conn.token)

    def test_duplicate_registration_is_refused(self):
        self.make_user("Rahul")
        conn = self.make_user("Amit")   # a second, separate client
        self.engine.handle(conn, {"type": "register", "username": "Rahul",
                                  "password": "AnotherPass1"})
        response = conn.last("error")
        self.assertEqual(response["code"], "username_taken")

    def test_short_username_rejected(self):
        conn = self.make_user("Placeholder")
        self.engine.handle(conn, {"type": "register", "username": "ab",
                                  "password": "GoodPass123"})
        self.assertEqual(conn.last("error")["code"], "bad_username")

    def test_username_with_spaces_rejected(self):
        conn = self.make_user("Placeholder")
        self.engine.handle(conn, {"type": "register", "username": "bad name",
                                  "password": "GoodPass123"})
        self.assertEqual(conn.last("error")["code"], "bad_username")

    def test_reserved_username_rejected(self):
        conn = self.make_user("Placeholder")
        self.engine.handle(conn, {"type": "register", "username": "admin",
                                  "password": "GoodPass123"})
        self.assertEqual(conn.last("error")["code"], "username_reserved")

    def test_weak_password_rejected(self):
        conn = self.make_user("Placeholder")
        self.engine.handle(conn, {"type": "register", "username": "ValidName",
                                  "password": "short"})
        self.assertEqual(conn.last("error")["code"], "weak_password")

    def test_password_never_comes_back(self):
        conn = self.make_user("Secretive")
        blob = repr(conn.sent)
        self.assertNotIn("TestPass123", blob)
        self.assertNotIn("password_hash", blob)


class LoginTests(EngineTestCase):
    def test_wrong_password_is_rejected_without_revealing_which_field(self):
        self.make_user("Priya")
        conn = self.make_user("Other")
        self.engine.handle(conn, {"type": "login", "username": "Priya",
                                  "password": "WrongPass123"})
        response = conn.last("login_response")
        self.assertFalse(response["success"])
        self.assertEqual(response["message"], "Invalid username or password")

    def test_unknown_user_gives_the_same_message(self):
        conn = self.make_user("Someone")
        self.engine.handle(conn, {"type": "login", "username": "Ghost",
                                  "password": "WrongPass123"})
        self.assertEqual(conn.last("login_response")["message"],
                         "Invalid username or password")

    def test_actions_require_login(self):
        from tests.helpers import FakeConnection
        conn = FakeConnection()
        self.manager.add(conn)
        self.engine.handle(conn, {"type": "get_users"})
        self.assertEqual(conn.last("error")["code"], "not_authenticated")

    def test_logout_invalidates_the_token(self):
        conn = self.make_user("Karan")
        token = conn.token
        self.engine.handle(conn, {"type": "logout"})
        self.assertIsNone(self.sessions.validate(token))
        self.assertFalse(conn.authenticated)

    def test_resume_session_with_token(self):
        conn = self.make_user("Resumer")
        token = conn.token
        self.engine.handle(conn, {"type": "logout"})

        from tests.helpers import FakeConnection
        fresh = FakeConnection()
        self.manager.add(fresh)
        self.engine.handle(fresh, {"type": "resume_session", "session_token": token})
        # The token was revoked at logout, so resume must fail.
        self.assertEqual(fresh.last("error")["code"], "invalid_token")

    def test_resume_session_works_while_token_is_live(self):
        conn = self.make_user("StillLive")
        token = conn.token

        from tests.helpers import FakeConnection
        fresh = FakeConnection()
        self.manager.add(fresh)
        self.engine.handle(fresh, {"type": "resume_session", "session_token": token})
        self.assertTrue(fresh.authenticated)
        self.assertEqual(fresh.username, "StillLive")


class ThrottleTests(EngineTestCase):
    def test_repeated_failures_lock_the_account(self):
        self.make_user("Victim")
        conn = self.make_user("Attacker")

        for _ in range(5):
            self.engine.handle(conn, {"type": "login", "username": "Victim",
                                      "password": "nope12345678"})
        self.engine.handle(conn, {"type": "login", "username": "Victim",
                                  "password": "nope12345678"})
        response = conn.last("login_response")
        self.assertEqual(response.get("code"), "throttled")
        self.assertIn("retry_after", response)

    def test_correct_password_is_also_blocked_during_lockout(self):
        self.make_user("Victim2")
        conn = self.make_user("Attacker2")
        for _ in range(6):
            self.engine.handle(conn, {"type": "login", "username": "Victim2",
                                      "password": "wrong123456"})
        self.engine.handle(conn, {"type": "login", "username": "Victim2",
                                  "password": "TestPass123"})
        self.assertEqual(conn.last("login_response").get("code"), "throttled")


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.limiter = RateLimiter(max_attempts=3, window_seconds=60,
                                   lockout_seconds=120, clock=lambda: self.now)

    def test_allows_until_threshold_then_blocks(self):
        for _ in range(3):
            self.assertTrue(self.limiter.check("k")[0])
            self.limiter.record_failure("k")
        allowed, retry_after = self.limiter.check("k")
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_lockout_expires(self):
        for _ in range(3):
            self.limiter.record_failure("k")
        self.assertFalse(self.limiter.check("k")[0])
        self.now += 121
        self.assertTrue(self.limiter.check("k")[0])

    def test_success_clears_failures(self):
        for _ in range(2):
            self.limiter.record_failure("k")
        self.limiter.record_success("k")
        self.assertEqual(self.limiter.failure_count("k"), 0)
        self.assertTrue(self.limiter.check("k")[0])

    def test_window_slides(self):
        self.limiter.record_failure("k")
        self.now += 61
        self.assertEqual(self.limiter.failure_count("k"), 0)


if __name__ == "__main__":
    unittest.main()
