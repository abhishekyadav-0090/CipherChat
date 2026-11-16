# Running CipherChat across devices on one Wi-Fi

Wi-Fi and sockets are not alternatives: Wi-Fi is the network, sockets are how the
two programs talk. Everything below assumes all devices are on the **same Wi-Fi
network** (a phone hotspot counts).

```
                    Wi-Fi router / hotspot
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   Laptop A             Laptop B              Phone C
   SERVER               CLIENT                CLIENT
   0.0.0.0:5000            │                     │
        └──────────── TCP + TLS ─────────────────┘
```

---

## 1. Start the server

```bash
cd backend
python tools/gen_certs.py        # once — creates certificates/
python main.py
```

The banner prints the addresses to hand to your friend:

```
  Frontend connects to:
    this machine     localhost:5000   TLS
    on your Wi-Fi    192.168.1.10:5000
  browser client:    wss://192.168.1.10:5443
```

That `192.168.1.10` is the address other devices use. **Not** `127.0.0.1` — that
only accepts connections from the server machine itself, which is the classic
reason a demo "works on my laptop and nowhere else".

---

## 2. Connect the clients

```bash
# from another laptop on the same Wi-Fi
python tools/cli_client.py --host 192.168.1.10

# or from the server machine
python tools/cli_client.py --host localhost
```

The client verifies the server against `certificates/ca.crt`. If you regenerate
certificates, copy the new `ca.crt` to every client machine (or to the frontend
project) — otherwise you get `CERTIFICATE_VERIFY_FAILED`, which is the system
working correctly.

---

## 3. The four things that break it

### 3.1 Client isolation (AP isolation) on the router

Most campus and hostel Wi-Fi has this on: devices on the same network cannot
reach each other at all. Symptom: the server is running, the IP is right, and
connections just hang.

Test from the second device:

```bash
ping 192.168.1.10
```

- Replies → isolation is off, good.
- No replies → use a **phone hotspot** instead. This is why the demo kit should
  always include one.

### 3.2 The firewall on the server machine

Linux (ufw): `sudo ufw allow 5000/tcp && sudo ufw allow 5443/tcp`
Windows: allow Python through the Windows Defender Firewall prompt the first time,
or add an inbound rule for ports 5000 and 5443.
macOS: System Settings → Network → Firewall → Options → allow incoming for Python.

### 3.3 Binding to the wrong address

`python main.py --host 127.0.0.1` is a loopback-only server. Use the default
`0.0.0.0`, which listens on every interface.

### 3.4 The wrong IP

Laptops often have several (Wi-Fi, Ethernet, Docker, VPN). The banner's "on your
Wi-Fi" line picks the outbound interface, which is usually right. If in doubt:

```bash
ip addr show        # Linux
ipconfig getifaddr en0   # macOS
ipconfig            # Windows
```

---

## 4. Certificates and IP addresses

The certificate's SAN list is fixed when it is generated. If the server's IP
changes (a new network, a new DHCP lease), the client will reject it with a
hostname mismatch. Fix it by regenerating with that IP:

```bash
python tools/gen_certs.py --extra-ip 192.168.1.10
```

`gen_certs.py` already includes `localhost`, the machine's hostname and every
local IPv4 it can find, so in most cases nothing needs changing. Adding a phone
hotspot's usual `192.168.43.x` range is a good idea before a demo:

```bash
python tools/gen_certs.py --extra-ip 192.168.43.1 --extra-ip 192.168.0.101
```

---

## 5. Same Wi-Fi, different networks, and the internet

| Setup | Works? | Note |
|---|---|---|
| Same Wi-Fi | Yes | The target demo |
| Phone hotspot | Yes | Most reliable; no isolation by default |
| Ethernet LAN | Yes | Same thing, different cable |
| Different networks (home ↔ hostel) | Only with port forwarding or a VPN | Both sides need a reachable address |
| Over the internet | Yes, with a public VPS | Run the server on the VPS; no code changes |
| No network at all | No | This backend is client–server; see the mesh project for that case |

The routing logic does not change between these. Only the address the client dials
changes — which is why `--host` and `--port` are flags, not constants.

---

## 6. Demo day checklist

1. Charge every device; disable sleep.
2. Bring a phone hotspot as a fallback network.
3. Generate certificates with every IP you might use, **before** the demo.
4. Start the server; confirm the banner shows a LAN address, not just localhost.
5. `ping` from each client device.
6. Register the demo accounts **in advance** — bcrypt is deliberately slow, and
   doing it live in front of an examiner looks like a hang (~0.3 s per login, but
   several at once on a weak laptop is noticeable).
7. Have `tools/load_test.py` ready to show five clients at once.
8. Have `logs/connection.log` open in a second window — the connection log is an
   explicit assignment requirement and it looks good on screen.
9. Do the Wireshark capture **before** the demo, not during it.
