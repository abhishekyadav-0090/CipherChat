# CipherChat — Backend

TLS socket chat server: multiple clients, authentication, message routing, SQLite
storage, connection logging, and the security demonstrations the assignment asks
for. Python 3.10+, no framework, no external server.

The frontend talks to it over **TCP + TLS** (desktop) or **WSS** (browser). The
contract is [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — read that before writing any
client code.

---

## Quick start

```bash
cd backend
pip install -r requirements.txt
python tools/gen_certs.py      # once: local CA + server certificate
python main.py                 # listens on 0.0.0.0:5000 (TLS) and :5443 (WSS)
```

In another terminal:

```bash
python tools/cli_client.py --host localhost
> /register abhishek MyPass123
> /login abhishek MyPass123
> /users
> /msg rahul Hello there
```

To connect from a phone or another laptop, use the Wi-Fi address the server prints
in its banner — see [`docs/WIFI_SETUP.md`](docs/WIFI_SETUP.md).

---

## What is implemented

| Module | Status | Where |
|---|---|---|
| 1. Socket server | Done | `server/server.py` — `socket/bind/listen/accept`, thread per client |
| 2. Multiple clients | Done | `server/connection_manager.py` — locked registry, per-user device sets |
| 3. Registration & authentication | Done | `authentication/` — bcrypt, sessions, logout, resume |
| 4. Message handling & routing | Done | `messaging/`, `server/message_router.py`, `server/protocol_engine.py` |
| 5. Encryption & security | Done | `security/tls_config.py`, `security/rate_limiter.py`, `security/input_validation.py` |
| 6. Database | Done | `database/` — 6 tables, all SQL in one place |
| 7. Connection logging | Done | `monitoring/logger.py` — three rotating logs |
| 8. Online users & sessions | Done | `server/connection_manager.py`, `authentication/session_manager.py` |
| 9. Error handling & reliability | Done | Graceful shutdown, timeouts, limits, per-thread isolation |
| 10. Security testing | Done | `tools/security_demo.py`, `docs/SECURITY_TESTS.md` |
| — Frontend contract | Done | `docs/PROTOCOL.md` |
| — WebSocket bridge for React | Done | `server/ws_server.py` (optional, same protocol) |
| — Test suite | Done | `tests/` — 92 tests |

Beyond the brief: group chat with membership checks, delivery and read receipts,
offline message replay, session resume without re-sending the password, and a
WebSocket front door so the same backend serves a browser.

---

## Layout

```
backend/
├── main.py                      entry point (flags: --port --plain --no-ws --host)
├── config.py                    every tunable, overridable by environment variable
├── server/
│   ├── server.py                listening socket, accept loop, graceful shutdown
│   ├── client_handler.py        one thread per client, TLS handshake, read loop
│   ├── framing.py               4-byte length-prefixed framing
│   ├── connection_manager.py    who is online, thread-safe registry
│   ├── message_router.py        delivery to live sockets, offline replay
│   ├── protocol_engine.py       the protocol: one request in, responses out
│   └── ws_server.py             optional wss:// bridge, reuses protocol_engine
├── authentication/
│   ├── auth.py                  register / login / logout policy
│   ├── password_manager.py      bcrypt (scrypt fallback), pre-hashed for length
│   └── session_manager.py       random tokens, stored only as SHA-256
├── security/
│   ├── tls_config.py            server and client contexts, TLS 1.2+ floor
│   ├── input_validation.py      every field, every frame
│   └── rate_limiter.py          sliding-window throttling
├── database/
│   ├── database.py              all SQL, per-thread connections, WAL
│   ├── schema.sql               6 tables + indexes
│   └── models.py                typed row wrappers
├── messaging/
│   ├── message_handler.py       may this message exist?
│   └── message_history.py       paginated history
├── monitoring/
│   ├── logger.py                app.log / security.log / connection.log
│   └── security_monitor.py      security counters for the dashboard
├── tools/
│   ├── gen_certs.py             local CA + server cert with the right SANs
│   ├── client_lib.py            reference client (thread-safe TLS)
│   ├── cli_client.py            interactive client
│   ├── load_test.py             five-plus clients at once, with latency
│   └── security_demo.py         the four security experiments, automated
├── tests/                       92 unittest cases
├── certificates/                generated; never commit server.key
├── logs/                        runtime
└── docs/
    ├── PROTOCOL.md              the frontend contract
    ├── SECURITY_TESTS.md        experiments, evidence, limitations
    └── WIFI_SETUP.md            multi-device demo setup
```

---

## Running the parts

```bash
# server
python main.py                       # TLS on 0.0.0.0:5000 + WSS on 5443
python main.py --port 6000           # different port
python main.py --no-ws               # TCP only
python main.py --plain               # NO TLS — only for the Wireshark comparison
python main.py --host 127.0.0.1      # this machine only

# clients
python tools/cli_client.py --host 192.168.1.10
python tools/cli_client.py --plain                    # match --plain server

# tests
python -m unittest discover -s tests -t . -v

# five clients at once, with measured latency
python tools/load_test.py --clients 5 --rounds 5

# security experiments
python tools/security_demo.py --all
python tools/security_demo.py --experiment impersonation
```

---

## How it is put together

```
client ──TLS──▶ client_handler (thread) ──▶ protocol_engine ──▶ database
                        ▲                        │
                        │                        ├──▶ message_router ──▶ other clients
                        │                        ├──▶ auth ──▶ session_manager
                        └────────────────────────┴──▶ monitoring (logs, counters)
```

`protocol_engine` is the only place that understands the protocol, and it is
transport-agnostic: the TCP handler and the WebSocket bridge both call
`engine.handle(conn, request)`. That is why the two transports cannot drift apart.

Three decisions worth defending in a viva:

**Thread per client, with one lock around the registry.** Simple, debuggable, and
plenty for tens of clients. The subtle part: an `ssl.SSLSocket` must not be read
and written at the same time, so sockets are non-blocking and every SSL operation
is serialised behind a per-connection lock, with `select()` waiting outside it.
That is a real bug in a lot of hand-written TLS servers — two threads, one SSL
object, intermittent deadlock.

**Persist before delivering.** A message is written to SQLite before any socket
send. If the process dies in between, the message is replayed at the recipient's
next login instead of vanishing.

**Identity comes from the session.** The client never says who it is. A `sender`
field in a request is treated as a forgery attempt, logged, and rejected.

---

## Database

Six tables: `users`, `sessions`, `messages`, `groups`, `group_members`,
`connection_logs`. WAL mode, foreign keys on, every query parameterised.

```bash
sqlite3 data/cipherchat.db ".tables"
sqlite3 data/cipherchat.db "SELECT username, created_at FROM users;"
sqlite3 data/cipherchat.db "SELECT timestamp, event_type, ip_address FROM connection_logs ORDER BY log_id DESC LIMIT 10;"
```

Stored passwords look like this — a bcrypt hash with a per-user salt, never the
password:

```
$2b$12$Q8k...  (60 characters)
```

---

## Configuration

Every value in `config.py` can be set by environment variable, e.g.

```bash
CIPHERCHAT_PORT=6000 CIPHERCHAT_LOG_LEVEL=DEBUG python main.py
CIPHERCHAT_LOGIN_LOCKOUT=30 python main.py       # short lockout for a demo
CIPHERCHAT_MAX_MESSAGE=500 python main.py
```

Useful ones: `CIPHERCHAT_PORT`, `CIPHERCHAT_HOST`, `CIPHERCHAT_DB`,
`CIPHERCHAT_CERT`/`CIPHERCHAT_KEY`, `CIPHERCHAT_LOGIN_ATTEMPTS`,
`CIPHERCHAT_LOGIN_LOCKOUT`, `CIPHERCHAT_SESSION_TTL`, `CIPHERCHAT_MAX_CLIENTS`.

---

## Test suite

```bash
python -m unittest discover -s tests -t . -v
```

| File | Covers |
|---|---|
| `test_database.py` | CRUD, duplicates, injection safety, pagination, sessions, groups, logs |
| `test_auth.py` | hashing, registration rules, login, throttling, rate-limiter windows |
| `test_messaging.py` | routing, offline storage and replay, impersonation, groups, history, presence |
| `test_security.py` | validation, framing (partial/oversized/malformed), redaction, TLS config |
| `test_server.py` | real sockets: TLS handshake, five concurrent clients, graceful shutdown |

`test_server.py` starts a real server on an ephemeral port and talks to it over
real TLS, so it catches integration bugs that unit tests cannot.

---

## Things that will bite you

1. **`--plain` is for the demo only.** It disables transport encryption. Never
   leave a server running that way.
2. **`certificates/server.key` must never be committed.** `.gitignore` covers it.
3. **Regenerate certificates when the server IP changes**, or clients get a
   hostname mismatch — see `docs/WIFI_SETUP.md`.
4. **Campus Wi-Fi with client isolation** blocks device-to-device traffic. Use a
   phone hotspot.
5. **bcrypt is deliberately slow** (~0.3 s per login). That is the point; do not
   "optimise" it by lowering the rounds.

---

## What is not done (and how to say it)

- **End-to-end encryption.** TLS protects the wire; the server can read bodies. E2EE
  would mean relaying ciphertext the server cannot decrypt — a different design.
- **Horizontal scaling.** Sessions and rate-limit counters are per-process. Two
  servers would need a shared store (Redis) and a message bus.
- **iOS client.** Out of scope.
- **Account recovery, 2FA, admin console.** Not asked for, and each is a project of
  its own.
