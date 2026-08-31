#!/usr/bin/env python3
"""End-to-end verification of the Postfix to Magika attachment-analysis path."""

from __future__ import annotations

import hashlib
import imaplib
import io
import json
import os
import smtplib
import ssl
import subprocess
import sys
import time
import uuid
import zipfile
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parents[1]
CA_FILE = LAB_DIR / "certs" / "ca" / "zzjh-mail-lab-ca.crt"
HOST = "127.0.0.1"
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


def build_zip() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("notice.txt", "ZZJH attachment type integration test")
    return stream.getvalue()


def send_disguised_attachment(subject: str, payload: bytes) -> None:
    message = EmailMessage()
    message["From"] = ALICE_EMAIL
    message["To"] = BOB_EMAIL
    message["Subject"] = subject
    message.set_content("附件扩展名和声明 MIME 均伪装为 PDF，实际内容是 ZIP。")
    message.add_attachment(
        payload,
        maintype="application",
        subtype="pdf",
        filename="invoice.pdf",
    )
    with smtplib.SMTP(HOST, 1587, timeout=30) as client:
        client.ehlo()
        client.starttls(context=TLS_CONTEXT)
        client.ehlo()
        client.login(ALICE_EMAIL, ALICE_PASSWORD)
        refused = client.send_message(message)
        if refused:
            raise AssertionError(f"SMTP refused recipients: {refused}")


def wait_for_message(subject: str, attempts: int = 30) -> bytes:
    for _ in range(attempts):
        with imaplib.IMAP4(HOST, 1143, timeout=30) as client:
            client.starttls(ssl_context=TLS_CONTEXT)
            client.login(BOB_EMAIL, BOB_PASSWORD)
            client.select("INBOX", readonly=True)
            status, data = client.search(None, "HEADER", "Subject", f'"{subject}"')
            if status == "OK" and data and data[0]:
                message_id = data[0].split()[-1]
                status, fetched = client.fetch(message_id, "(RFC822)")
                if status != "OK":
                    raise AssertionError("IMAP message fetch failed")
                for item in fetched:
                    if isinstance(item, tuple) and isinstance(item[1], bytes):
                        return item[1]
        time.sleep(1)
    raise AssertionError("analyzed message did not arrive")


def load_result(trace_id: str) -> dict:
    code = """
import json, sys
path = '/data/results/attachment-analysis.jsonl'
with open(path, encoding='utf-8') as stream:
    matches = [json.loads(line) for line in stream if line.strip()]
for item in reversed(matches):
    if item.get('trace_id') == sys.argv[1]:
        print(json.dumps(item, ensure_ascii=False))
        raise SystemExit(0)
raise SystemExit(2)
"""
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "attachment-analyzer",
            "python",
            "-c",
            code,
            trace_id,
        ],
        cwd=LAB_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"analysis JSON record not found: {completed.stderr.strip()}"
        )
    return json.loads(completed.stdout)


def main() -> int:
    token = uuid.uuid4().hex[:12]
    subject = f"ZZJH-MAGIKA-{token}"
    payload = build_zip()
    send_disguised_attachment(subject, payload)
    raw_message = wait_for_message(subject)
    message = BytesParser(policy=policy.default).parsebytes(raw_message)

    summary = str(message["X-ZZJH-Attachment-Analysis"])
    types = str(message["X-ZZJH-Attachment-Types"])
    trace_id = str(message["X-ZZJH-Trace-ID"])
    if not all(value in summary for value in ("count=1", "mismatch=1", "errors=0")):
        raise AssertionError(f"unexpected analysis summary: {summary}")
    if "1=zip/" not in types or not types.endswith("/mismatch"):
        raise AssertionError(f"unexpected type summary: {types}")
    if len(trace_id) != 32:
        raise AssertionError(f"unexpected trace ID: {trace_id!r}")

    attachments = list(message.iter_attachments())
    if len(attachments) != 1:
        raise AssertionError(f"expected one attachment, got {len(attachments)}")
    if attachments[0].get_payload(decode=True) != payload:
        raise AssertionError("attachment bytes changed during analysis")

    record = load_result(trace_id)
    attachment = record["attachments"][0]
    if attachment["detected"]["label"] != "zip":
        raise AssertionError(f"unexpected Magika label: {attachment['detected']}")
    if set(attachment["mismatch_reasons"]) != {
        "declared_mime",
        "filename_extension",
    }:
        raise AssertionError(
            f"unexpected mismatch reasons: {attachment['mismatch_reasons']}"
        )
    if attachment["sha256"] != hashlib.sha256(payload).hexdigest():
        raise AssertionError("structured result SHA-256 is incorrect")

    print(
        "PASS Magika attachment analysis: "
        f"trace_id={trace_id}, detected=zip, declared=application/pdf, "
        "extension=pdf, mismatch=true, bytes_preserved=true"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
