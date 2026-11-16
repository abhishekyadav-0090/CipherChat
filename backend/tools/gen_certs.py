"""Generate a local CA and a server certificate with the right SANs.

Why a CA instead of a self-signed leaf? Because the client must *verify* the
server. If the server cert is self-signed, the client either trusts everything
(insecure) or pins one exact file. With a tiny local CA, the client trusts
ca.crt and verification stays fully on — which is the thing you want to be able
to demonstrate.

    python tools/gen_certs.py                 # into ./certificates
    python tools/gen_certs.py --days 30
    python tools/gen_certs.py --extra-ip 192.168.1.42

SANs always include localhost, 127.0.0.1, the machine's hostname and every
local IPv4, so phones on the same Wi-Fi can connect by IP without a hostname
mismatch error.
"""
from __future__ import annotations

import argparse
import ipaddress
import shutil
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


def local_ipv4_addresses() -> list[str]:
    addrs: set[str] = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        addrs.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    return sorted(addrs)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate CipherChat TLS certificates")
    parser.add_argument("--out", default=str(config.CERT_DIR), help="output directory")
    parser.add_argument("--days", type=int, default=825, help="validity in days")
    parser.add_argument("--hostname", default="cipherchat.local", help="certificate CN")
    parser.add_argument("--extra-ip", action="append", default=[],
                        help="additional IP SAN (repeatable)")
    args = parser.parse_args(argv)

    if shutil.which("openssl") is None:
        print("[!] openssl not found on PATH. Install it, or generate the certs on "
              "another machine and copy certificates/ across.")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ca_key, ca_crt = out / "ca.key", out / "ca.crt"
    srv_key, srv_csr, srv_crt = out / "server.key", out / "server.csr", out / "server.crt"
    ext = out / "server.ext"

    ips = local_ipv4_addresses() + [ip for ip in args.extra_ip if ip]
    # de-duplicate, keep order
    seen, unique_ips = set(), []
    for ip in ips:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue
        if ip not in seen:
            seen.add(ip)
            unique_ips.append(ip)

    san_lines = [f"DNS.1 = localhost", f"DNS.2 = {args.hostname}",
                 f"DNS.3 = {socket.gethostname()}"]
    san_lines += [f"IP.{i} = {ip}" for i, ip in enumerate(unique_ips, start=1)]
    ext.write_text("basicConstraints = CA:FALSE\n"
                   "keyUsage = digitalSignature, keyEncipherment\n"
                   "extendedKeyUsage = serverAuth\n"
                   "subjectAltName = @alt_names\n\n[alt_names]\n"
                   + "\n".join(san_lines) + "\n", encoding="utf-8")

    print(f"[*] Generating certificates in {out}")
    run(["openssl", "genrsa", "-out", str(ca_key), "2048"])
    run(["openssl", "req", "-x509", "-new", "-nodes", "-key", str(ca_key), "-sha256",
         "-days", str(args.days), "-out", str(ca_crt),
         "-subj", "/O=CipherChat/CN=CipherChat Local CA"])
    run(["openssl", "genrsa", "-out", str(srv_key), "2048"])
    run(["openssl", "req", "-new", "-key", str(srv_key), "-out", str(srv_csr),
         "-subj", f"/O=CipherChat/CN={args.hostname}"])
    run(["openssl", "x509", "-req", "-in", str(srv_csr), "-CA", str(ca_crt),
         "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(srv_crt),
         "-days", str(args.days), "-sha256", "-extfile", str(ext)])

    try:
        srv_key.chmod(0o600)
        ca_key.chmod(0o600)
    except OSError:
        pass
    srv_csr.unlink(missing_ok=True)
    (out / "ca.srl").unlink(missing_ok=True)
    ext.unlink(missing_ok=True)

    fingerprint = run(["openssl", "x509", "-in", str(srv_crt), "-noout", "-fingerprint",
                       "-sha256"]).stdout.strip().split("=", 1)[-1]

    print(f"[+] CA certificate      {ca_crt}")
    print(f"[+] Server certificate  {srv_crt}")
    print(f"[+] Server key          {srv_key}")
    print(f"    SHA-256 fingerprint  {fingerprint}")
    print(f"    Valid SANs           localhost, {args.hostname}, "
          f"{socket.gethostname()}, {', '.join(unique_ips)}")
    print("\n    Start the server:   python main.py")
    print("    Connect a client:   python tools/cli_client.py --host localhost")
    print("\n    Give the frontend ca.crt — it must verify, not ignore, the certificate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
