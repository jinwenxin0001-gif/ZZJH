#!/usr/bin/env python3
"""Confirm all published laboratory ports are bound only to loopback."""

from __future__ import annotations

import re
import os
import subprocess
import sys


ROUNDCUBE_PORT = int(os.environ.get("ROUNDCUBE_HOST_PORT", "8080"))
EXPECTED_PORTS = {2525, 1587, 1143, 1993, 1110, 1995, ROUNDCUBE_PORT}


def main() -> int:
    output = subprocess.check_output(["ss", "-ltnH"], text=True)
    found: dict[int, str] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        local = fields[3]
        match = re.search(r":(\d+)$", local)
        if not match:
            continue
        port = int(match.group(1))
        if port in EXPECTED_PORTS:
            found[port] = local

    missing = EXPECTED_PORTS - found.keys()
    if missing:
        print(f"FAIL expected listeners are missing: {sorted(missing)}", file=sys.stderr)
        return 1

    unsafe = {port: address for port, address in found.items() if not address.startswith("127.0.0.1:")}
    if unsafe:
        print(f"FAIL laboratory ports are not loopback-only: {unsafe}", file=sys.stderr)
        return 1

    for port in sorted(found):
        print(f"PASS loopback-only listener {found[port]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
