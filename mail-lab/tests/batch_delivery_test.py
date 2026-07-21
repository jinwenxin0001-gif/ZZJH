#!/usr/bin/env python3
"""Submit a batch of messages and verify that every message reaches IMAP."""

from __future__ import annotations

import imaplib
import os
import smtplib
import ssl
import sys
import time
import uuid
from email.message import EmailMessage
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parents[1]
CA_FILE = LAB_DIR / "certs" / "ca" / "zzjh-mail-lab-ca.crt"
HOST = "127.0.0.1"


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


ALICE_EMAIL = required("ALICE_EMAIL")
ALICE_PASSWORD = required("ALICE_PASSWORD")
BOB_EMAIL = required("BOB_EMAIL")
BOB_PASSWORD = required("BOB_PASSWORD")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "1000"))
TLS_CONTEXT = ssl.create_default_context(cafile=str(CA_FILE))


def submit_batch(batch_id: str) -> float:
    started = time.monotonic()
    with smtplib.SMTP(HOST, 1587, timeout=30) as client:
        client.ehlo()
        client.starttls(context=TLS_CONTEXT)
        client.ehlo()
        client.login(ALICE_EMAIL, ALICE_PASSWORD)

        for sequence in range(1, BATCH_SIZE + 1):
            message = EmailMessage()
            message["From"] = ALICE_EMAIL
            message["To"] = BOB_EMAIL
            message["Subject"] = f"ZZJH-BATCH-{batch_id}-{sequence:04d}"
            message["X-ZZJH-Batch-ID"] = batch_id
            message.set_content(
                f"ZZJH mail-lab batch delivery test\n"
                f"batch={batch_id}\nsequence={sequence}\n"
            )
            refused = client.send_message(message)
            if refused:
                raise AssertionError(
                    f"SMTP refused message {sequence}: {refused}"
                )
            if sequence % 100 == 0 or sequence == BATCH_SIZE:
                print(f"PROGRESS submitted {sequence}/{BATCH_SIZE}", flush=True)

    return time.monotonic() - started


def wait_for_delivery(batch_id: str, attempts: int = 90) -> tuple[int, float]:
    started = time.monotonic()
    last_count = 0
    for _ in range(attempts):
        with imaplib.IMAP4(HOST, 1143, timeout=30) as client:
            client.starttls(ssl_context=TLS_CONTEXT)
            status, _ = client.login(BOB_EMAIL, BOB_PASSWORD)
            if status != "OK":
                raise AssertionError("IMAP login failed")
            status, _ = client.select("INBOX", readonly=True)
            if status != "OK":
                raise AssertionError("IMAP INBOX selection failed")
            status, data = client.search(
                None, "HEADER", "X-ZZJH-Batch-ID", f'"{batch_id}"'
            )
            if status != "OK":
                raise AssertionError("IMAP batch search failed")
            last_count = len(data[0].split()) if data and data[0] else 0

        print(
            f"PROGRESS delivered {last_count}/{BATCH_SIZE}",
            flush=True,
        )
        if last_count == BATCH_SIZE:
            return last_count, time.monotonic() - started
        if last_count > BATCH_SIZE:
            raise AssertionError(
                f"Found too many messages for unique batch {batch_id}: {last_count}"
            )
        time.sleep(2)

    return last_count, time.monotonic() - started


def main() -> int:
    if BATCH_SIZE < 1:
        raise ValueError("BATCH_SIZE must be positive")

    batch_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    submit_seconds = submit_batch(batch_id)
    count, delivery_seconds = wait_for_delivery(batch_id)
    if count != BATCH_SIZE:
        raise AssertionError(
            f"Only {count}/{BATCH_SIZE} messages reached Bob's INBOX"
        )

    rate = BATCH_SIZE / submit_seconds
    print(
        "PASS batch delivery: "
        f"accepted={BATCH_SIZE}, delivered={count}, "
        f"submit_seconds={submit_seconds:.2f}, "
        f"submit_rate={rate:.2f} msg/s, "
        f"delivery_wait_seconds={delivery_seconds:.2f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
