#!/usr/bin/env python3
"""Print Bob's INBOX message count for the persistence test."""

from __future__ import annotations

import imaplib
import os
import ssl
from pathlib import Path


lab_dir = Path(__file__).resolve().parents[1]
context = ssl.create_default_context(cafile=str(lab_dir / "certs/ca/zzjh-mail-lab-ca.crt"))

with imaplib.IMAP4("127.0.0.1", 1143, timeout=20) as client:
    client.starttls(ssl_context=context)
    client.login(os.environ["BOB_EMAIL"], os.environ["BOB_PASSWORD"])
    status, data = client.select("INBOX", readonly=True)
    if status != "OK":
        raise SystemExit("Unable to select Bob's INBOX")
    print(data[0].decode())
