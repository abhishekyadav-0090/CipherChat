"""Database layer tests: the guarantees the rest of the backend relies on."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import EngineTestCase  # noqa: F401  (sets sys.path)
from database.database import Database, DuplicateUserError, utc_now


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "db.sqlite")
        self.db.init_schema()

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    # ── users ─────────────────────────────────────────────────────────────
    def test_create_and_fetch_user(self):
        user_id = self.db.create_user("Abhishek", "hash$abc")
        row = self.db.get_user_by_id(user_id)
        self.assertEqual(row["username"], "Abhishek")
        self.assertEqual(row["password_hash"], "hash$abc")
        self.assertIsNotNone(row["created_at"])

    def test_duplicate_username_raises(self):
        self.db.create_user("Rahul", "hash$1")
        with self.assertRaises(DuplicateUserError):
            self.db.create_user("Rahul", "hash$2")

    def test_username_is_case_insensitive_for_lookup(self):
        self.db.create_user("Priya", "hash$1")
        self.assertIsNotNone(self.db.get_user_by_username("priya"))
        with self.assertRaises(DuplicateUserError):
            self.db.create_user("PRIYA", "hash$2")

    def test_sql_injection_in_username_is_inert(self):
        """Parameterised queries: this string is data, not SQL."""
        evil = "x'; DROP TABLE users; --"
        user_id = self.db.create_user(evil, "hash$1")
        self.assertEqual(self.db.get_user_by_id(user_id)["username"], evil)
        self.assertEqual(self.db.count_users(), 1)   # table still there

    # ── messages ──────────────────────────────────────────────────────────
    def test_message_roundtrip_and_status(self):
        alice = self.db.create_user("Alice", "h")
        bob = self.db.create_user("Bob", "h")
        message_id = self.db.save_message(alice, "hello", receiver_id=bob)
        row = self.db.get_message(message_id)
        self.assertEqual(row["body"], "hello")
        self.assertEqual(row["status"], "stored")

        self.db.set_message_status(message_id, "delivered")
        self.assertEqual(self.db.get_message(message_id)["status"], "delivered")

    def test_conversation_is_bidirectional_and_ordered(self):
        alice = self.db.create_user("Alice", "h")
        bob = self.db.create_user("Bob", "h")
        self.db.save_message(alice, "one", receiver_id=bob)
        self.db.save_message(bob, "two", receiver_id=alice)
        self.db.save_message(alice, "three", receiver_id=bob)

        rows = self.db.get_conversation(alice, bob, limit=10)
        self.assertEqual([r["body"] for r in rows], ["one", "two", "three"])

    def test_conversation_excludes_other_peoples_messages(self):
        alice = self.db.create_user("Alice", "h")
        bob = self.db.create_user("Bob", "h")
        eve = self.db.create_user("Eve", "h")
        self.db.save_message(eve, "secret", receiver_id=bob)

        rows = self.db.get_conversation(alice, bob, limit=10)
        self.assertEqual(rows, [])

    def test_pagination_with_before_id(self):
        alice = self.db.create_user("Alice", "h")
        bob = self.db.create_user("Bob", "h")
        ids = [self.db.save_message(alice, f"m{i}", receiver_id=bob) for i in range(5)]

        page = self.db.get_conversation(alice, bob, limit=2, before_id=ids[3])
        self.assertEqual([r["body"] for r in page], ["m1", "m2"])

    def test_undelivered_only_returns_stored(self):
        alice = self.db.create_user("Alice", "h")
        bob = self.db.create_user("Bob", "h")
        first = self.db.save_message(alice, "a", receiver_id=bob)
        self.db.save_message(alice, "b", receiver_id=bob)
        self.db.set_message_status(first, "delivered")

        pending = self.db.get_undelivered(bob)
        self.assertEqual([r["body"] for r in pending], ["b"])

    # ── sessions ──────────────────────────────────────────────────────────
    def test_session_lifecycle(self):
        user_id = self.db.create_user("Karan", "h")
        self.db.create_session(user_id, "hash-token", "2099-01-01T00:00:00+00:00", "127.0.0.1")
        self.assertIsNotNone(self.db.get_session("hash-token"))

        self.assertTrue(self.db.revoke_session("hash-token"))
        self.assertIsNone(self.db.get_session("hash-token"))

    def test_expired_sessions_are_purged(self):
        user_id = self.db.create_user("Amit", "h")
        self.db.create_session(user_id, "old", "2000-01-01T00:00:00+00:00")
        self.assertEqual(self.db.purge_expired_sessions(), 1)

    # ── groups ────────────────────────────────────────────────────────────
    def test_group_membership(self):
        owner = self.db.create_user("Owner", "h")
        member = self.db.create_user("Member", "h")
        group_id = self.db.create_group("Hostel", owner)

        self.assertTrue(self.db.is_group_member(group_id, owner))   # creator joins
        self.assertFalse(self.db.is_group_member(group_id, member))

        self.db.add_group_member(group_id, member)
        self.assertTrue(self.db.is_group_member(group_id, member))
        self.assertEqual(len(self.db.get_group_members(group_id)), 2)
        self.assertEqual(len(self.db.get_user_groups(member)), 1)

    # ── logs ──────────────────────────────────────────────────────────────
    def test_connection_logs(self):
        user_id = self.db.create_user("Logger", "h")
        self.db.log_connection("LOGIN_SUCCESS", user_id, "10.0.0.5", "test")
        rows = self.db.get_connection_logs(limit=10)
        self.assertEqual(rows[0]["event_type"], "LOGIN_SUCCESS")
        self.assertEqual(rows[0]["ip_address"], "10.0.0.5")
        self.assertEqual(len(self.db.get_connection_logs(event_type="LOGIN_SUCCESS")), 1)
        self.assertEqual(len(self.db.get_connection_logs(event_type="LOGOUT")), 0)

    def test_utc_now_is_iso_format(self):
        self.assertRegex(utc_now(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


if __name__ == "__main__":
    unittest.main()
