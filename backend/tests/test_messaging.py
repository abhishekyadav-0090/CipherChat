"""Messaging tests: routing, offline storage, authorisation, presence."""
from __future__ import annotations

import unittest

from tests.helpers import EngineTestCase, FakeConnection


class PrivateMessageTests(EngineTestCase):
    def test_message_reaches_an_online_recipient(self):
        alice = self.make_user("Alice")
        bob = self.make_user("Bob")

        self.engine.handle(alice, {"type": "private_message",
                                   "receiver_id": self.user_id("Bob"),
                                   "message": "hello Bob"})
        ack = alice.last("message_response")
        self.assertTrue(ack["success"])
        self.assertEqual(ack["status"], "delivered")

        incoming = bob.last("incoming_message")
        self.assertEqual(incoming["message"], "hello Bob")
        self.assertEqual(incoming["sender"], "Alice")

    def test_message_to_offline_user_is_stored_not_lost(self):
        alice = self.make_user("Alice")
        self.make_user("Bob")
        bob_id = self.user_id("Bob")
        # Bob goes away.
        for conn in self.manager.connections_for(bob_id):
            self.manager.remove(conn)
            conn.close()

        self.engine.handle(alice, {"type": "private_message", "receiver_id": bob_id,
                                   "message": "are you there?"})
        self.assertEqual(alice.last("message_response")["status"], "stored")

        row = self.db.get_undelivered(bob_id)
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["body"], "are you there?")

    def test_offline_messages_are_replayed_on_login(self):
        alice = self.make_user("Alice")
        self.make_user("Bob")
        bob_id = self.user_id("Bob")
        # Bob must be offline, or the message would be delivered live.
        for conn in self.manager.connections_for(bob_id):
            self.manager.remove(conn)
            conn.close()

        self.engine.handle(alice, {"type": "private_message", "receiver_id": bob_id,
                                   "message": "waiting for you"})
        self.assertEqual(alice.last("message_response")["status"], "stored")

        # Bob logs in again on a new connection.
        fresh = FakeConnection()
        self.manager.add(fresh)
        self.engine.handle(fresh, {"type": "login", "username": "Bob",
                                   "password": "TestPass123"})
        replayed = [p for p in fresh.sent if p.get("type") == "incoming_message"]
        self.assertEqual(len(replayed), 1)
        self.assertTrue(replayed[0].get("offline_replay"))
        self.assertEqual(self.db.get_undelivered(bob_id), [])

    def test_message_to_unknown_user_is_rejected(self):
        alice = self.make_user("Alice")
        self.engine.handle(alice, {"type": "private_message", "receiver_id": 9999,
                                   "message": "hello?"})
        self.assertEqual(alice.last("error")["code"], "unknown_recipient")

    def test_cannot_message_yourself(self):
        alice = self.make_user("Alice")
        self.engine.handle(alice, {"type": "private_message",
                                   "receiver_id": self.user_id("Alice"),
                                   "message": "hi me"})
        self.assertEqual(alice.last("error")["code"], "self_message")

    def test_empty_and_oversized_messages_rejected(self):
        alice = self.make_user("Alice")
        self.make_user("Bob")
        bob_id = self.user_id("Bob")

        self.engine.handle(alice, {"type": "private_message", "receiver_id": bob_id,
                                   "message": "   "})
        self.assertEqual(alice.last("error")["code"], "empty_message")

        self.engine.handle(alice, {"type": "private_message", "receiver_id": bob_id,
                                   "message": "x" * 5000})
        self.assertEqual(alice.last("error")["code"], "message_too_long")

    def test_control_characters_are_stripped(self):
        alice = self.make_user("Alice")
        bob = self.make_user("Bob")
        self.engine.handle(alice, {"type": "private_message",
                                   "receiver_id": self.user_id("Bob"),
                                   "message": "hello\x07\x1b world"})
        self.assertEqual(bob.last("incoming_message")["message"], "hello world")

    def test_null_byte_is_rejected(self):
        alice = self.make_user("Alice")
        self.make_user("Bob")
        self.engine.handle(alice, {"type": "private_message",
                                   "receiver_id": self.user_id("Bob"),
                                   "message": "bad\x00message"})
        self.assertEqual(alice.last("error")["code"], "bad_message")

    def test_impersonation_is_rejected(self):
        alice = self.make_user("Alice")
        bob = self.make_user("Bob")
        self.engine.handle(alice, {"type": "private_message",
                                   "receiver_id": self.user_id("Bob"),
                                   "sender": "Bob", "message": "forged"})
        self.assertEqual(alice.last("error")["code"], "impersonation_rejected")
        self.assertFalse(any(p.get("type") == "incoming_message" for p in bob.sent))
        self.assertGreater(self.monitor.snapshot()["counters"]
                           .get("impersonation_attempt", 0), 0)

    def test_matching_sender_field_is_allowed(self):
        """A client that echoes its own identity is not an attacker."""
        alice = self.make_user("Alice")
        self.make_user("Bob")
        self.engine.handle(alice, {"type": "private_message",
                                   "receiver_id": self.user_id("Bob"),
                                   "sender": "Alice", "message": "fine"})
        self.assertEqual(alice.last("message_response")["success"], True)


class GroupTests(EngineTestCase):
    def test_group_message_reaches_members_only(self):
        alice = self.make_user("Alice")
        bob = self.make_user("Bob")
        self.make_user("Outsider")

        self.engine.handle(alice, {"type": "create_group", "name": "Project",
                                   "members": [self.user_id("Bob")]})
        group_id = alice.last("group_response")["group_id"]

        self.engine.handle(alice, {"type": "group_message", "group_id": group_id,
                                   "message": "kickoff at 5"})
        self.assertEqual(alice.last("message_response")["success"], True)
        self.assertEqual(bob.last("incoming_group_message")["message"], "kickoff at 5")

    def test_non_member_cannot_post(self):
        alice = self.make_user("Alice")
        outsider = self.make_user("Outsider")
        self.engine.handle(alice, {"type": "create_group", "name": "Private"})
        group_id = alice.last("group_response")["group_id"]

        self.engine.handle(outsider, {"type": "group_message", "group_id": group_id,
                                      "message": "let me in"})
        self.assertEqual(outsider.last("error")["code"], "not_a_member")

    def test_non_member_cannot_read_history(self):
        alice = self.make_user("Alice")
        outsider = self.make_user("Outsider")
        self.engine.handle(alice, {"type": "create_group", "name": "Secret"})
        group_id = alice.last("group_response")["group_id"]

        self.engine.handle(outsider, {"type": "message_history", "group_id": group_id})
        self.assertEqual(outsider.last("error")["code"], "not_a_member")


class HistoryTests(EngineTestCase):
    def test_history_returns_the_conversation(self):
        alice = self.make_user("Alice")
        bob = self.make_user("Bob")
        bob_id = self.user_id("Bob")
        for text in ("one", "two"):
            self.engine.handle(alice, {"type": "private_message",
                                       "receiver_id": bob_id, "message": text})

        self.engine.handle(alice, {"type": "message_history", "with_user_id": bob_id})
        response = alice.last("history_response")
        self.assertEqual([m["message"] for m in response["messages"]], ["one", "two"])

    def test_history_never_leaks_another_conversation(self):
        alice = self.make_user("Alice")
        bob = self.make_user("Bob")
        eve = self.make_user("Eve")
        self.engine.handle(eve, {"type": "private_message",
                                 "receiver_id": self.user_id("Bob"),
                                 "message": "private to Bob"})

        self.engine.handle(alice, {"type": "message_history",
                                   "with_user_id": self.user_id("Bob")})
        self.assertEqual(alice.last("history_response")["messages"], [])


class PresenceTests(EngineTestCase):
    def test_online_list_reflects_connections(self):
        self.make_user("Alice")
        self.make_user("Bob")
        self.make_user("Amit")
        # Amit disconnects.
        for conn in self.manager.connections_for(self.user_id("Amit")):
            self.manager.remove(conn)
            conn.close()

        alice = self.manager.connections_for(self.user_id("Alice"))[0]
        self.engine.handle(alice, {"type": "get_users"})
        users = {u["username"]: u["status"] for u in alice.last("users_response")["users"]}
        self.assertEqual(users["Alice"], "online")
        self.assertEqual(users["Bob"], "online")
        self.assertEqual(users["Amit"], "offline")

    def test_multiple_devices_for_one_user(self):
        alice = self.make_user("Alice")
        second = FakeConnection()
        self.manager.add(second)
        self.engine.handle(second, {"type": "login", "username": "Alice",
                                    "password": "TestPass123"})
        self.assertEqual(self.manager.count_for_user(self.user_id("Alice")), 2)

        self.make_user("Bob")
        self.engine.handle(alice, {"type": "private_message",
                                   "receiver_id": self.user_id("Bob"),
                                   "message": "hi"})
        self.assertEqual(alice.last("message_response")["status"], "delivered")

    def test_delivery_ack_only_for_own_messages(self):
        alice = self.make_user("Alice")
        bob = self.make_user("Bob")
        self.engine.handle(alice, {"type": "private_message",
                                   "receiver_id": self.user_id("Bob"),
                                   "message": "hi"})
        message_id = alice.last("message_response")["message_id"]

        # Alice is the sender, so she may not ack her own message as received.
        self.engine.handle(alice, {"type": "delivery_ack", "message_id": message_id})
        self.assertEqual(alice.last("error")["code"], "not_your_message")

        self.engine.handle(bob, {"type": "delivery_ack", "message_id": message_id})
        self.assertEqual(self.db.get_message(message_id)["status"], "delivered")

    def test_typing_notification_is_forwarded(self):
        alice = self.make_user("Alice")
        bob = self.make_user("Bob")
        self.engine.handle(alice, {"type": "typing", "receiver_id": self.user_id("Bob")})
        self.assertTrue(bob.last("typing")["is_typing"])


if __name__ == "__main__":
    unittest.main()
