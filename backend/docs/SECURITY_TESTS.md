# Security experiments — what to run, what to show

Everything here is reproducible. Run the scripts for the automated evidence, and
do the Wireshark capture by hand once (it is the one thing a script cannot do for
you).

Start the server first:

```bash
python main.py
```

Run everything:

```bash
python tools/security_demo.py --all
```

Run one experiment:

```bash
python tools/security_demo.py --experiment impersonation
```

| # | Experiment | What it proves |
|---|---|---|
| 1 | TLS on, and the certificate is verified | Traffic is encrypted and the client cannot be fooled by an impostor |
| 2 | Brute-force throttling | Repeated wrong passwords are blocked, even for the right password |
| 3 | Impersonation attempt | A forged `sender` field is refused; identity comes from the session |
| 4 | Tampering with the stream | A modified byte breaks the connection instead of changing a message |
| 5 | Input limits | Oversized, malformed and unknown requests are rejected |

---

## Experiment 1 — eavesdropping, plain TCP vs TLS

This is the headline demonstration. It needs two captures.

### 1a. Capture the plaintext session

Terminal 1 — server **without** TLS:

```bash
python main.py --plain --no-ws
```

Terminal 2 — a client that logs in over the same plaintext socket:

```bash
python tools/cli_client.py --plain
> /register demo_user DemoPass123
> /login demo_user DemoPass123
```

Terminal 3 — capture (needs root):

```bash
sudo tcpdump -i any -A -s 0 'tcp port 5000' -w plain.pcap
```

Now open `plain.pcap` in Wireshark, right-click any packet → **Follow → TCP
Stream**. You will see the JSON in clear text: `"type":"login"`,
`"username":"demo_user"`, and the password.

### 1b. Capture the TLS session

Terminal 1 — server with TLS:

```bash
python main.py
```

Terminal 2:

```bash
python tools/cli_client.py
> /register tls_user DemoPass123
> /login tls_user DemoPass123
```

Terminal 3:

```bash
sudo tcpdump -i any -A -s 0 'tcp port 5000' -w tls.pcap
```

Follow the TCP stream again. You now see TLS record bytes — `16 03 03` handshake
records followed by opaque application data. The username and password are not
recoverable.

### 1c. What to say about it

> The same request, the same server, the same client. The only difference is one
> flag. In the first capture the password is readable; in the second it is not.
> TLS gives us confidentiality and integrity in transit — a modified packet is
> detected, not silently accepted.

And be precise about the limit:

> This is transport encryption, not end-to-end encryption. The server can read
> message bodies because it stores and routes them. E2EE would mean the server
> relays ciphertext it cannot decrypt — that is the next project, not this one.

### 1d. Verification matters (automated)

`python tools/security_demo.py --experiment unverified` shows the flip side: a
client that skips certificate verification connects happily to anything. Our
client sets `CERT_REQUIRED` and `check_hostname=True`, so it would refuse an
impostor. That is the difference between "encrypted" and "secure".

---

## Experiment 2 — brute-force protection

```bash
python tools/security_demo.py --experiment bruteforce
```

Expected output: five failures are allowed, then `throttled` with a `retry_after`,
and — importantly — **the correct password is also refused** while the lockout is
active. That is what makes it a real control rather than a speed bump.

Evidence to show:

```bash
grep -E "LOGIN_FAILED|LOGIN_THROTTLED" logs/security.log | tail -20
```

Design notes worth saying out loud:

- Two independent limits: **5 attempts per account** and **20 per IP** in the same
  window. The IP limit is deliberately looser, because every device behind one
  campus NAT shares an address — a strict IP limit would let one attacker lock out
  the whole hostel.
- Failures and successes return the **same message** ("Invalid username or
  password") so the API cannot be used to discover which usernames exist.
- Counters live in memory, so they reset when the server restarts. A production
  deployment would put them in Redis. Say this before you are asked.

To watch the lockout expire without waiting 15 minutes:

```bash
CIPHERCHAT_LOGIN_LOCKOUT=30 python main.py
```

---

## Experiment 3 — impersonation

```bash
python tools/security_demo.py --experiment impersonation
```

The script logs in as user A, then sends a message claiming `"sender": "B"`.

Expected:

```
server said: error / impersonation_rejected / Sender identity does not match the authenticated session
control (no forged sender): message_response accepted
```

Why it works: `ProtocolEngine._reject_impersonation()` compares any claimed
sender against the authenticated session before the message is even validated.
The `sender` field is accepted in the payload *only* so the attempt can be
detected and logged.

Manual version — edit the JSON by hand in the CLI client or with a raw socket, and
watch `logs/security.log`:

```bash
grep IMPERSONATION logs/security.log
```

---

## Experiment 4 — message tampering

```bash
python tools/security_demo.py --experiment tampering
```

The script connects over TLS and injects bytes into the encrypted stream. The
connection dies instead of delivering a different message: TLS records carry a
MAC, so a modified byte fails authentication and the record is discarded.

The comparison worth making: on the `--plain` server the same injection is simply
interpreted as whatever bytes arrived — there is nothing to detect a change.

---

## Experiment 5 — input limits

```bash
python tools/security_demo.py --experiment limits
```

Four checks: a 2-character username, malformed JSON, a 4 500-character message,
and an unknown message type. Each is rejected with a specific code rather than
crashing the handler thread.

Additional things to demonstrate if asked:

```bash
# SQL injection is inert — the username is data, not SQL
> /register "x'; DROP TABLE users; --" DemoPass123
# the server rejects it on the username charset rule, and every query is parameterised anyway

# oversized frame: the server refuses before allocating memory
python - <<'PY'
import socket, struct
s = socket.create_connection(("localhost", 5000))
s.sendall(struct.pack("!I", 10_000_000))   # declare a 10 MB frame
print(s.recv(1024))
PY
```

---

## Where the evidence lives

| Evidence | Location |
|---|---|
| Connection and auth events | `logs/connection.log` |
| Security events (failures, throttling, impersonation) | `logs/security.log` |
| Errors and stack traces | `logs/app.log` |
| Login and message records | `data/cipherchat.db` (table `connection_logs`) |
| Capture files | `plain.pcap`, `tls.pcap` |

Inspect the database directly for the report:

```bash
sqlite3 data/cipherchat.db "SELECT timestamp, event_type, ip_address, detail FROM connection_logs ORDER BY log_id DESC LIMIT 20;"
sqlite3 data/cipherchat.db "SELECT COUNT(*) FROM users;"
sqlite3 data/cipherchat.db "SELECT user_id, username, substr(password_hash,1,20) || '...' FROM users;"
```

The last one is the point: what is stored is a bcrypt hash with its own salt, not
a password. Two users with the same password have different hashes.

---

## Honest limitations to state before you are asked

1. **TLS ≠ end-to-end encryption.** The server can read message bodies. It has to,
   to store history and route to offline users.
2. **Rate-limit counters are in memory**, so a restart clears a lockout.
3. **No account lockout notification** — the attacker gets a throttle, but the
   account owner is not told.
4. **Single process.** Two server instances would not share sessions or limits
   without a shared store.
5. **The CA is local and self-signed.** Fine for a demo; a real deployment needs a
   publicly trusted certificate (Let's Encrypt) or certificate pinning.
6. **The key file must stay private.** `gen_certs.py` sets `600` permissions; if
   `certificates/server.key` is committed to git, the whole TLS story is void.
