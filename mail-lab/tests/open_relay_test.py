#!/usr/bin/env python3
"""Verify that the laboratory SMTP endpoint does not relay external mail."""

from __future__ import annotations

import smtplib
import sys


def main() -> int:
    with smtplib.SMTP("127.0.0.1", 2525, timeout=20) as client:
        client.ehlo("untrusted.example.net")
        code, response = client.mail("outsider@example.net")
        if code >= 400:
            print(f"PASS external sender rejected before RCPT: {code} {response.decode(errors='replace')}")
            return 0
        code, response = client.rcpt("victim@example.org")
        if code < 400:
            print(
                f"FAIL server accepted an external relay recipient: {code} {response.decode(errors='replace')}",
                file=sys.stderr,
            )
            return 1
        print(f"PASS open relay rejected: {code} {response.decode(errors='replace')}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
