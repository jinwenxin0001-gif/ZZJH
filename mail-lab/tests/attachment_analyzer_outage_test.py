#!/usr/bin/env python3
"""Verify that Postfix defers mail while the analyzer is unavailable."""

from __future__ import annotations

import imaplib
import os
import smtplib
import ssl
import subprocess
import sys
import time
import uuid
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parents[1]
CA_FILE = LAB_DIR / "certs" / "ca" / "zzjh-mail-lab-ca.crt"
TLS_CONTEXT = ssl.create_default_context(cafile=str(CA_FILE))


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


ALICE_EMAIL = required("ALICE_EMAIL")
ALICE_PASSWORD = required("ALICE_PASSWORD")
BOB_EMAIL = required("BOB_EMAIL")
BOB_PASSWORD = required("BOB_PASSWORD")


def compose(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *arguments],
        cwd=LAB_DIR,
        text=True,
        capture_output=True,
        check=check,
    )


def send(subject: str) -> None:
    message = EmailMessage()
    message["From"] = ALICE_EMAIL
    message["To"] = BOB_EMAIL
    message["Subject"] = subject
    message.set_content("This message must wait for the analyzer to recover.")
    with smtplib.SMTP("127.0.0.1", 1587, timeout=30) as client:
        client.ehlo()
        client.starttls(context=TLS_CONTEXT)
        client.ehlo()
        client.login(ALICE_EMAIL, ALICE_PASSWORD)
        refused = client.send_message(message)
        if refused:
            raise AssertionError(f"SMTP refused recipients: {refused}")


def find_message(subject: str) -> bytes | None:
    with imaplib.IMAP4("127.0.0.1", 1143, timeout=30) as client:
        client.starttls(ssl_context=TLS_CONTEXT)
        client.login(BOB_EMAIL, BOB_PASSWORD)
        client.select("INBOX", readonly=True)
        status, data = client.search(None, "HEADER", "Subject", f'"{subject}"')
        if status != "OK" or not data or not data[0]:
            return None
        message_id = data[0].split()[-1]
        status, fetched = client.fetch(message_id, "(RFC822)")
        if status != "OK":
            return None
        for item in fetched:
            if isinstance(item, tuple) and isinstance(item[1], bytes):
                return item[1]
    return None


def wait_analyzer_healthy(attempts: int = 40) -> None:
    for _ in range(attempts):
        completed = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{end}}",
                "zzjh-attachment-analyzer",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip() == "healthy":
            return
        time.sleep(1)
    raise AssertionError("attachment analyzer did not become healthy")


def main() -> int:
    subject = f"ZZJH-ANALYZER-OUTAGE-{uuid.uuid4().hex[:12]}"
    compose("exec", "-T", "mailserver", "postqueue", "-f")
    compose("stop", "attachment-analyzer")
    try:
        send(subject)
        time.sleep(3)
        if find_message(subject) is not None:
            raise AssertionError("message bypassed the unavailable analyzer")
        queue = compose(
            "exec", "-T", "mailserver", "postqueue", "-p"
        ).stdout
        if BOB_EMAIL not in queue:
            raise AssertionError("message was not retained in the Postfix queue")
    finally:
        compose("start", "attachment-analyzer", check=False)

    wait_analyzer_healthy()
    compose("exec", "-T", "mailserver", "postqueue", "-f")
    raw_message = None
    for _ in range(30):
        raw_message = find_message(subject)
        if raw_message is not None:
            break
        time.sleep(1)
    if raw_message is None:
        raise AssertionError("deferred message was not delivered after recovery")

    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    summary = str(message["X-ZZJH-Attachment-Analysis"])
    if not all(value in summary for value in ("count=0", "errors=0")):
        raise AssertionError(f"recovered message lacks analysis result: {summary}")
    print(
        "PASS analyzer outage handling: message deferred without bypass and "
        "delivered after analyzer recovery"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
