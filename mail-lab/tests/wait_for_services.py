#!/usr/bin/env python3
"""Wait until mail protocols and, optionally, Roundcube are reachable."""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
import time
import urllib.request
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parents[1]
TLS_CONTEXT = ssl.create_default_context(
    cafile=str(LAB_DIR / "certs" / "ca" / "zzjh-mail-lab-ca.crt")
)
MAIL_CHECKS = (
    (2525, b"220", False),
    (1587, b"220", False),
    (1143, b"* OK", False),
    (1993, b"* OK", True),
    (1110, b"+OK", False),
    (1995, b"+OK", True),
)


def protocol_ready(port: int, expected_prefix: bytes, implicit_tls: bool) -> bool:
    try:
        raw_socket = socket.create_connection(("127.0.0.1", port), timeout=3)
        raw_socket.settimeout(3)
        if implicit_tls:
            connection = TLS_CONTEXT.wrap_socket(raw_socket, server_hostname="127.0.0.1")
        else:
            connection = raw_socket
        with connection:
            banner = connection.recv(512)
            return banner.startswith(expected_prefix)
    except (OSError, ssl.SSLError):
        return False


def http_ready() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mail-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        mail_ok = all(protocol_ready(*check) for check in MAIL_CHECKS)
        web_ok = args.mail_only or http_ready()
        if mail_ok and web_ok:
            print("PASS required services are reachable")
            return 0
        time.sleep(3)
    print("FAIL services did not become reachable before timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
