# CipherChat — Frontend ↔ Backend Protocol Contract

**Version 1.0 · backend v1.0.0**

This is the document to agree on before either side writes code. If the frontend
follows this exactly, integration is an afternoon; if it improvises, integration
is three days of "works on my machine".

Two transports carry the *same* JSON. Pick one:

| Transport | Address | Use when |
|---|---|---|
| **TCP + TLS** | `tcp://<server-ip>:5000` | Desktop frontend (Tkinter, PyQt, a Python/Node client). Demonstrates raw socket programming. |
| **WebSocket + TLS** | `wss://<server-ip>:5443` | Browser frontend (React, Vue, plain JS). A browser cannot open a raw TCP socket. |

Both are served by the same process at the same time. The JSON is byte-identical;
only the framing differs (see §2).

---

## 1. The one rule

**The server decides who you are.** You never tell it.

- Identity comes from the authenticated session, not from a `sender` field.
- Authorisation (can this user read this conversation, post to this group) is
  decided on the server, always.
- If the frontend sends a `sender` field that contradicts the session, the request
  is rejected with `impersonation_rejected` and logged as a security event. This
  is deliberate: it is one of the four attacks we have to demonstrate.

---

## 2. Framing

### 2.1 TCP: 4-byte length prefix

A TCP stream has no message boundaries. Every frame is:

```
┌──────────────────┬────────────────────────────┐
│ 4 bytes, big-end │ N bytes, UTF-8 JSON        │
│ unsigned length  │ (no trailing newline)      │
└──────────────────┴────────────────────────────┘
```

Python:

```python
import json, struct

def encode(payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return struct.pack("!I", len(body)) + body

def frames_from(buffer: bytearray):
    """Yield complete payloads, leave the partial tail in the buffer."""
    while len(buffer) >= 4:
        (length,) = struct.unpack_from("!I", buffer, 0)
        if len(buffer) < 4 + length:
            return
        yield bytes(buffer[4:4 + length])
        del buffer[:4 + length]
```

JavaScript (Node):

```js
const buf = Buffer.alloc(4);
buf.writeUInt32BE(Buffer.byteLength(json), 0);
socket.write(Buffer.concat([buf, Buffer.from(json, 'utf8')]));
```

Limits: one frame may not exceed **65536 bytes**. A frame declaring more is
rejected and the connection closed (`frame_error`). A zero-length frame is a
protocol violation.

### 2.2 WebSocket: one JSON object per frame

No length prefix, no newline — send the JSON object as one WebSocket text frame.
`max_size` on the server is also 65536.

---

## 3. Lifecycle

```
connect ──▶ register ──▶ login ──▶ (use the app) ──▶ logout ──▶ disconnect
                          │
                          └──▶ session_token  (reconnect later with resume_session)
```

You may send `ping` before logging in. Everything else needs a session.

---

## 4. Messages, in full

### 4.1 `register`

```json
→ {"type": "register", "username": "Abhishek", "password": "correct horse battery"}
← {"type": "register_response", "success": true, "message": "Registration successful",
   "user_id": 1, "username": "Abhishek"}
← {"type": "error", "code": "username_taken", "message": "Username already taken",
   "request_type": "register"}
```

Username: 3–24 characters, must start with a letter, letters/digits/`_` only.
Password: 8–128 characters. Registration does **not** log you in — send `login`
next.

### 4.2 `login`

```json
→ {"type": "login", "username": "Abhishek", "password": "correct horse battery"}
← {"type": "login_response", "success": true, "message": "Login successful",
   "user_id": 1, "username": "Abhishek",
   "session_token": "9f3c...", "expires_at": "2026-11-17T09:30:00+00:00"}
← {"type": "login_response", "success": false, "message": "Invalid username or password",
   "code": "invalid_credentials"}
← {"type": "login_response", "success": false,
   "message": "Too many failed attempts. Try again later.",
   "code": "throttled", "retry_after": 840}
```

Store `session_token` (memory or secure storage). Never log it. After a successful
login the server pushes any messages that arrived while you were offline
(`incoming_message` with `"offline_replay": true`), then a `presence` update.

### 4.3 `resume_session` — reconnect without the password

```json
→ {"type": "resume_session", "session_token": "9f3c..."}
← {"type": "resume_response", "success": true, "user_id": 1, "username": "Abhishek"}
```

Use this after a dropped connection or an app restart. If the token expired or was
revoked you get `error` / `invalid_token` and must log in again.

### 4.4 `logout`

```json
→ {"type": "logout"}
← {"type": "logout_response", "success": true, "message": "Logged out"}
```

The token is revoked server-side; the connection stays open but anonymous.

### 4.5 `private_message`

```json
→ {"type": "private_message", "receiver_id": 2, "message": "Hello Rahul!"}
← {"type": "message_response", "success": true, "message_id": 501,
   "receiver_id": 2, "receiver": "Rahul", "status": "delivered"}
```

`status` is `delivered` when the recipient had a live connection, `stored` when
they were offline. **Both mean the message is safe** — `stored` ones are replayed
on their next login. Show a single tick for `stored`, two for `delivered`.

The recipient receives, on their own connection:

```json
← {"type": "incoming_message", "message_id": 501, "sender_id": 1, "sender": "Abhishek",
   "receiver_id": 2, "message": "Hello Rahul!", "status": "delivered",
   "timestamp": "2026-11-16T09:31:02+00:00"}
```

### 4.6 `group_message`

```json
→ {"type": "group_message", "group_id": 3, "message": "kickoff at 5"}
← {"type": "message_response", "success": true, "message_id": 502,
   "group_id": 3, "status": "delivered", "recipients": 4}
```

Members receive `incoming_group_message` (same fields plus `group_name`). Posting
to a group you are not in returns `not_a_member`.

### 4.7 `get_users`

```json
→ {"type": "get_users"}
← {"type": "users_response", "online_count": 2, "users": [
     {"user_id": 1, "username": "Abhishek", "status": "online", "last_seen_at": "..."},
     {"user_id": 2, "username": "Rahul",    "status": "offline", "last_seen_at": "..."}
   ]}
```

### 4.8 `message_history`

```json
→ {"type": "message_history", "with_user_id": 2, "limit": 50}
→ {"type": "message_history", "with_user_id": 2, "limit": 50, "before_id": 480}
→ {"type": "message_history", "group_id": 3, "limit": 50}
← {"type": "history_response", "success": true, "with_user_id": 2,
   "with_username": "Rahul", "count": 2, "messages": [
     {"message_id": 499, "sender_id": 1, "sender": "Abhishek", "receiver_id": 2,
      "group_id": null, "message": "hi", "status": "delivered", "timestamp": "..."}
   ]}
```

Ordered oldest→newest. Paginate with `before_id` (the oldest `message_id` you
already have), not with offsets — offsets shift while new messages arrive.
`limit` is 1–200, default 50.

### 4.9 `typing`

```json
→ {"type": "typing", "receiver_id": 2, "is_typing": true}
← (to the recipient) {"type": "typing", "sender_id": 1, "sender": "Abhishek",
                      "is_typing": true}
```

Fire and forget: no response to the sender. Debounce to ~1/second.

### 4.10 `delivery_ack` / `mark_read`

```json
→ {"type": "delivery_ack", "message_id": 501}
→ {"type": "mark_read",   "message_id": 501}
← (to the original sender) {"type": "delivery_ack", "message_id": 501,
                            "receiver_id": 2, "status": "delivered"}
← (to the original sender) {"type": "read_receipt", "message_id": 501,
                            "reader_id": 2, "status": "read"}
```

Only the recipient may acknowledge a message; anyone else gets `not_your_message`.

### 4.11 `create_group` / `get_groups`

```json
→ {"type": "create_group", "name": "Project Team", "members": [2, 3]}
← {"type": "group_response", "success": true, "group_id": 3, "name": "Project Team",
   "members": ["Abhishek", "Rahul", "Amit"]}
→ {"type": "get_groups"}
← {"type": "groups_response", "groups": [
     {"group_id": 3, "name": "Project Team", "owner_id": 1,
      "members": ["Abhishek", "Rahul", "Amit"]}]}
```

### 4.12 `ping` and `server_info`

```json
→ {"type": "ping"}
← {"type": "pong", "server_time": "2026-11-16T09:32:00+00:00"}
```

Send a `ping` every 30 s. The server drops connections silent for 300 s.

`server_info` (no auth needed) returns version, transport, TLS state, live stats
and security counters — handy for a dashboard panel.

### 4.13 Server-initiated messages

```json
← {"type": "presence", "online_count": 2,
   "online": [{"user_id": 1, "username": "Abhishek"}, {"user_id": 2, "username": "Rahul"}]}
← {"type": "server_shutdown", "message": "Server is shutting down"}
```

`presence` is pushed after every login/logout/disconnect. `server_shutdown` means
close cleanly and reconnect later.

---

## 5. Error codes

Every error is `{"type": "error", "code": "...", "message": "...", "request_type": "..."}`.
Show `message` to the user; branch on `code`.

| Code | Meaning | What the UI should do |
|---|---|---|
| `not_authenticated` | No session on this connection | Go to the login screen |
| `invalid_credentials` | Wrong username or password | "Invalid username or password" |
| `username_taken` | Username already registered | Highlight the field |
| `username_reserved` | Reserved name (`admin`, `root`, …) | Suggest another |
| `bad_username` / `weak_password` | Failed validation | Show `message` verbatim |
| `throttled` | Too many failed logins | Disable the form, show `retry_after` |
| `unknown_recipient` | No such user | Remove from the contact list |
| `unknown_group` / `not_a_member` | Group problem | Refresh the group list |
| `self_message` | Tried to message yourself | Disable that action |
| `empty_message` / `message_too_long` | Bad body | Enforce the limit client-side too |
| `bad_message` | Null byte or wrong type | — |
| `impersonation_rejected` | Forged `sender` field | A bug — never send `sender` |
| `not_your_message` | Acked someone else's message | A bug |
| `invalid_token` | Session expired/revoked | Log in again |
| `malformed_json` | Frame was not valid JSON | A bug |
| `unknown_type` | Unsupported `type` | A bug |
| `frame_too_large` / `frame_error` | Framing violation | Close and reconnect |
| `server_full` | Connection limit reached | Retry later |
| `idle_timeout` | 300 s of silence | Reconnect and `resume_session` |
| `server_error` | Unexpected server fault | Generic error, retry |

---

## 6. Limits the frontend must respect

| Limit | Value |
|---|---|
| Frame size | 65 536 bytes |
| Message length | 4 000 characters |
| Username | 3–24 chars, starts with a letter |
| Password | 8–128 chars |
| Group name | 1–48 chars |
| History page | 1–200 messages |
| Idle timeout | 300 s (send `ping` every 30 s) |
| Session lifetime | 24 h |

---

## 7. Minimal React client

```js
// useChat.js — the whole integration in one hook
import { useCallback, useEffect, useRef, useState } from 'react';

export function useChat(url = 'wss://192.168.1.10:5443') {
  const ws = useRef(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState([]);
  const [online, setOnline] = useState([]);
  const me = useRef(null);

  useEffect(() => {
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case 'incoming_message':
        case 'incoming_group_message':
          setMessages((prev) => [...prev, msg]);
          break;
        case 'presence':
          setOnline(msg.online);
          break;
        case 'login_response':
          if (msg.success) me.current = msg.user_id;
          break;
        default:
          break;
      }
    };

    return () => socket.close();
  }, [url]);

  const send = useCallback((payload) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(payload));
    }
  }, []);

  return { connected, messages, online, me: me.current, send };
}
```

Note: the browser will refuse a self-signed certificate. For the demo, open
`https://<server-ip>:5443` once in the browser and accept the warning, or import
`certificates/ca.crt` into the browser's trust store. Do **not** work around this
by disabling verification in code.

---

## 8. Integration checklist

- [ ] Length-prefix framing on TCP (4-byte big-endian), or one JSON per WS frame
- [ ] `ping` every 30 s
- [ ] Never send `sender` / `sender_id` in a request
- [ ] Keep `session_token` in memory; use `resume_session` on reconnect
- [ ] Treat `status: "stored"` as success, not failure
- [ ] Re-render the contact list on `presence`
- [ ] Show `error.message` to the user, branch on `error.code`
- [ ] Enforce the same length limits client-side for a good experience
