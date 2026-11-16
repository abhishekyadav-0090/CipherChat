# CipherChat — Frontend

Encrypted real-time messaging, built as a real client for the CipherChat Python
backend. React 19 + TypeScript + Vite 6 + Tailwind 4 + Framer Motion.

Design language: neo-brutalist — 2px borders, hard offset shadows, extrabold
tight type, near-black surfaces, neon-green primary with a pastel-purple accent.

---

## 1. Run it

```bash
# 1. backend (in the CipherChat repo)
cd CipherChat/backend
pip install -r requirements.txt
python tools/gen_certs.py      # once — creates certificates/
python main.py                 # TLS on :5000, WSS on :5443

# 2. this app
cd frontend
npm install
cp .env.example .env
npm run dev                    # http://localhost:5173
```

Register two accounts — one in a normal window, one in a private window — and
they appear in each other's sidebar immediately.

### Trusting the certificate (one-time)

The backend uses a local CA, so the browser refuses the socket until you trust it:

- open `https://localhost:5443` once and accept the warning, **or**
- import `CipherChat/backend/certificates/ca.crt` into your trust store.

Do **not** work around this by disabling verification in code — verified TLS is
part of what the project is graded on.

### Other machines

```env
VITE_SERVER_URL=wss://192.168.1.10:5443
```

Regenerate the certificate with that IP (`python tools/gen_certs.py --extra-ip
192.168.1.10`) or the hostname check fails — which is the check working.

---

## 2. What is implemented

**Authentication** — register, log in, log out, session resume, throttling
countdown, inline field validation mirroring the server's rules.

**Messaging** — direct messages and group chat, optimistic send with real status
(`sending → sent → delivered → read`), offline queueing, history loaded per
conversation, delivery and read receipts.

**Presence** — live online/offline from server `presence` events, typing
indicators in both the sidebar and the chat header.

**Resilience** — automatic reconnect with exponential backoff and jitter, keepalive
that detects half-open sockets, session resume without re-entering a password,
send blocked (with a visible banner) while disconnected.

**Groups** — create a group, pick members, group message fan-out, member list.

**Settings** — four accents, live server stats (`server_info`), security summary.

---

## 3. Security, on the client side

| Concern | What this app does |
|---|---|
| Session token storage | `sessionStorage`, never `localStorage` — it dies with the tab. Cleared on logout and on `invalid_token`. |
| Token in logs | Never logged. No `console.log` of any payload. |
| XSS | Message bodies are rendered as text nodes. There is no `dangerouslySetInnerHTML` anywhere in the codebase. |
| Injection into the protocol | Every request is a typed object built by the app; user input never becomes part of a request's structure. |
| Oversized input | `maxLength` on inputs plus a hard 4,000-character cap in the composer, matching the server's limit. |
| Certificate handling | Verification stays on. The app surfaces a clear failure instead of silently downgrading. |
| Auth failures | The server's message is shown; `retry_after` drives a countdown so the user is not left clicking a dead button. |
| Session death | `invalid_token` / `not_authenticated` drop the session and return to the login screen rather than showing stale data. |

Honest limit, stated in the UI too: this is **transport** encryption. The server
can read message bodies because it stores history and delivers to offline users.
End-to-end encryption would be a different architecture.

---

## 4. How it is put together

```
AuthScreen ─┐
            ├─▶ useChat ──▶ ChatSocket ──▶ wss://server:5443 ──▶ protocol_engine.py
AppShell ───┘
```

```
src/
├── lib/
│   ├── protocol.ts     types for every request/response/error + validation rules
│   ├── socket.ts       transport: correlation, reconnect, keepalive, resume
│   ├── motion.ts       shared Framer Motion presets
│   └── format.ts       cn(), initials, clock/day formatting
├── hooks/useChat.ts    all state and actions — the only place that touches the socket
└── components/
    ├── ui/             Button, Input, Avatar, Modal, Toasts
    ├── auth/           AuthScreen
    ├── shell/          AppShell (layout, mobile drawer, nav)
    ├── sidebar/        Sidebar + new-chat / new-group dialogs
    ├── chat/           ChatView, MessageList, MessageBubble, Composer
    ├── panel/          InfoPanel
    └── settings/       SettingsView
```

Three rules worth keeping if you extend it:

1. **The server decides status.** Nothing is marked delivered because a timer
   elapsed; `delivery_ack` and `read_receipt` do that.
2. **`stored` is success.** An offline recipient means the message is queued on
   the server — shown as `sent`, not as an error.
3. **One socket, one hook.** Components never open a connection or call `fetch`;
   they call `useChat` actions.

---

## 5. Motion

Framer Motion, with `MotionConfig reducedMotion="user"` at the root — so every
animation is automatically skipped for anyone whose OS asks for reduced motion,
and the CSS layer repeats the guarantee with a `prefers-reduced-motion` block.

What animates, and why:

- **Screen change** (auth ↔ app): 200 ms cross-fade, because it is a context switch.
- **Messages**: spring entry, 8 px rise — it shows *which* bubble is new without
  making the reader wait.
- **Sidebar rows**: `layout` animation so re-ordering on a new message is legible
  instead of a jump.
- **Tabs / nav**: `layoutId` shared-element underline.
- **Modals**: scale + fade, 150–220 ms, with Escape and backdrop close.
- **Toasts**: slide in from the right, stack with `layout`.
- **Typing dots**: staggered CSS keyframes (cheap, no JS per frame).

Nothing exceeds ~350 ms. Motion never blocks input.

---

## 6. What was verified, and what was not

**Verified here:**

- `tsc --noEmit` clean across the whole project (strict mode, `noUnusedLocals`).
- Server-side render of the auth screen — 11.7 KB of HTML, all expected content.
- Server-side render of the authenticated shell with stub data — sidebar, chat
  list, message bubbles, info panel and composer all present (9/9 probes).
- The transport, compiled and driven from Node against the **live Python
  backend**: connect, register, login, second peer, `get_users`, send, delivery,
  typing, bad-credential rejection, `resume_session`, history, `server_info` —
  11/11 passed.

**Not verified:** the visual result in a browser. The production build could not
run in my environment (the Tailwind WASM engine needs more memory than the
sandbox allows), so **no one has looked at these pixels yet**. Run `npm run dev`
and check: the auth screen, bubble contrast (neon fill, black text), the composer,
and Settings. Everything is token-driven in `src/index.css`, so a colour change is
one line.

---

## 7. Next steps

1. **File and image transfer** — needs a chunked upload protocol on the server
   first; the UI deliberately has no media affordances until then.
2. **End-to-end encryption** — the honest upgrade: X25519 key exchange in the
   client, server relays ciphertext it cannot read.
3. **Notifications** — `Notification` API when the tab is backgrounded.
4. **Message search** — the server would need a `search` request type.
