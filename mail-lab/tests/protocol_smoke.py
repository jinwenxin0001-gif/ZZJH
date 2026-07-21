#!/usr/bin/env python3
"""End-to-end SMTP, IMAP, POP3, TLS and attachment smoke tests."""

from __future__ import annotations

import imaplib
import os
import poplib
import smtplib
import ssl
import sys
import time
import uuid
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
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
POP3_EMAIL = required("POP3_EMAIL")
POP3_PASSWORD = required("POP3_PASSWORD")

TLS_CONTEXT = ssl.create_default_context(cafile=str(CA_FILE))


def pass_line(message: str) -> None:
    print(f"PASS {message}", flush=True)


def send_mail(recipient: str, subject: str, include_attachment: bool) -> None:
    message = EmailMessage()
    message["From"] = ALICE_EMAIL
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content("这是一封用于 ZZJH 邮件安全实验环境的协议验证邮件。\n")
    message.add_alternative(
        "<html><body><p>这是一封用于 <strong>ZZJH</strong> 邮件安全实验环境的协议验证邮件。</p></body></html>",
        subtype="html",
    )
    if include_attachment:
        payload = b"ZZJH mail-lab attachment smoke test\n"
        message.add_attachment(
            payload,
            maintype="application",
            subtype="octet-stream",
            filename="smoke-test.txt",
        )

    with smtplib.SMTP(HOST, 1587, timeout=20) as client:
        client.ehlo()
        client.starttls(context=TLS_CONTEXT)
        client.ehlo()
        client.login(ALICE_EMAIL, ALICE_PASSWORD)
        refused = client.send_message(message)
        if refused:
            raise AssertionError(f"SMTP refused recipients: {refused}")


def wait_for_imap(subject: str, attempts: int = 20) -> bytes:
    for _ in range(attempts):
        with imaplib.IMAP4(HOST, 1143, timeout=20) as client:
            client.starttls(ssl_context=TLS_CONTEXT)
            status, _ = client.login(BOB_EMAIL, BOB_PASSWORD)
            if status != "OK":
                raise AssertionError("IMAP login failed")
            status, _ = client.select("INBOX")
            if status != "OK":
                raise AssertionError("IMAP INBOX selection failed")
            status, data = client.search(None, "HEADER", "Subject", f'"{subject}"')
            if status == "OK" and data and data[0]:
                message_id = data[0].split()[-1]
                status, fetched = client.fetch(message_id, "(RFC822)")
                if status != "OK":
                    raise AssertionError("IMAP message fetch failed")
                for item in fetched:
                    if isinstance(item, tuple) and isinstance(item[1], bytes):
                        return item[1]
        time.sleep(2)
    raise AssertionError(f"Message did not arrive in IMAP mailbox: {subject}")


def verify_message(raw_message: bytes, subject: str) -> None:
    parsed = BytesParser(policy=policy.default).parsebytes(raw_message)
    if parsed["Subject"] != subject:
        raise AssertionError(f"Unexpected subject: {parsed['Subject']!r}")
    attachments = list(parsed.iter_attachments())
    if len(attachments) != 1:
        raise AssertionError(f"Expected one attachment, got {len(attachments)}")
    attachment = attachments[0]
    if attachment.get_filename() != "smoke-test.txt":
        raise AssertionError(f"Unexpected attachment name: {attachment.get_filename()!r}")
    if attachment.get_payload(decode=True) != b"ZZJH mail-lab attachment smoke test\n":
        raise AssertionError("Attachment content changed during delivery")


def wait_for_pop3(subject: str, attempts: int = 20) -> None:
    for _ in range(attempts):
        client = poplib.POP3(HOST, 1110, timeout=20)
        try:
            client.stls(context=TLS_CONTEXT)
            client.user(POP3_EMAIL)
            client.pass_(POP3_PASSWORD)
            _, entries, _ = client.list()
            for entry in reversed(entries):
                number = int(entry.split()[0])
                _, lines, _ = client.retr(number)
                raw = b"\r\n".join(lines) + b"\r\n"
                parsed = BytesParser(policy=policy.default).parsebytes(raw)
                if parsed["Subject"] == subject:
                    return
        finally:
            try:
                client.quit()
            except Exception:
                pass
        time.sleep(2)
    raise AssertionError(f"Message did not arrive in POP3 mailbox: {subject}")


def verify_implicit_tls() -> None:
    with imaplib.IMAP4_SSL(HOST, 1993, ssl_context=TLS_CONTEXT, timeout=20) as client:
        status, _ = client.login(BOB_EMAIL, BOB_PASSWORD)
        if status != "OK":
            raise AssertionError("IMAPS login failed")

    client = poplib.POP3_SSL(HOST, 1995, context=TLS_CONTEXT, timeout=20)
    try:
        client.user(POP3_EMAIL)
        client.pass_(POP3_PASSWORD)
    finally:
        client.quit()


def main() -> int:
    token = uuid.uuid4().hex[:12]
    imap_subject = f"ZZJH-SMOKE-IMAP-{token}"
    pop3_subject = f"ZZJH-SMOKE-POP3-{token}"

    send_mail(BOB_EMAIL, imap_subject, include_attachment=True)
    pass_line("SMTP submission with STARTTLS and authentication")

    raw_message = wait_for_imap(imap_subject)
    pass_line("IMAP STARTTLS login and message retrieval")
    verify_message(raw_message, imap_subject)
    pass_line("UTF-8 body and attachment integrity")

    send_mail(POP3_EMAIL, pop3_subject, include_attachment=False)
    wait_for_pop3(pop3_subject)
    pass_line("POP3 STLS login and message retrieval")

    verify_implicit_tls()
    pass_line("IMAPS and POP3S certificate verification")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
