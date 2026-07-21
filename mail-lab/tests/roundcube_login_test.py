#!/usr/bin/env python3
"""Log into Roundcube, send a message, and verify delivery over IMAP."""

from __future__ import annotations

import html
import http.cookiejar
import imaplib
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


URL = "http://127.0.0.1:8080/"
LAB_DIR = Path(__file__).resolve().parents[1]
CA_FILE = LAB_DIR / "certs" / "ca" / "zzjh-mail-lab-ca.crt"


class BrowserSession:
    def __init__(self) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
        )

    def request(
        self, url: str, form: dict[str, str] | None = None
    ) -> tuple[str, str]:
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        request = urllib.request.Request(url, data=data)
        with self.opener.open(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            page = response.read().decode(charset, errors="replace")
            return response.geturl(), page


def hidden_value(page: str, name: str) -> str:
    match = re.search(rf'name="{re.escape(name)}"\s+value="([^"]*)"', page)
    if not match:
        raise AssertionError(f"Roundcube field was not found: {name}")
    return html.unescape(match.group(1))


def wait_for_delivery(subject: str, attempts: int = 20) -> None:
    context = ssl.create_default_context(cafile=str(CA_FILE))
    for _ in range(attempts):
        with imaplib.IMAP4("127.0.0.1", 1143, timeout=20) as client:
            client.starttls(ssl_context=context)
            client.login(os.environ["BOB_EMAIL"], os.environ["BOB_PASSWORD"])
            client.select("INBOX", readonly=True)
            status, data = client.search(None, "HEADER", "Subject", f'"{subject}"')
            if status == "OK" and data and data[0]:
                return
        time.sleep(1)
    raise AssertionError("Roundcube message did not reach Bob's IMAP mailbox")


def main() -> int:
    session = BrowserSession()
    _, page = session.request(URL)

    token = hidden_value(page, "_token")
    payload = {
        "_token": token,
        "_task": "login",
        "_action": "login",
        "_timezone": "Asia/Shanghai",
        "_url": "",
        "_user": os.environ["ALICE_EMAIL"],
        "_pass": os.environ["ALICE_PASSWORD"],
    }
    page_url, page = session.request(URL, payload)

    authenticated = (
        "_task=logout" in page
        or 'rcmail.set_env("task","mail")' in page
        or "rcmail.set_env('task','mail')" in page
    )
    login_failed = "loginform" in page.lower() or "_task=login" in page_url
    if not authenticated or login_failed:
        print(f"FAIL Roundcube login did not reach the mailbox: {page_url}", file=sys.stderr)
        return 1

    print("PASS Roundcube authenticated login reached the mailbox")

    _, page = session.request(f"{URL}?_task=mail&_action=compose")
    identity_match = re.search(
        r'<select[^>]+name="_from"[^>]*>.*?<option[^>]+value="([^"]+)"',
        page,
        re.DOTALL,
    )
    if not identity_match:
        raise AssertionError("Roundcube sender identity was not found")

    subject = f"ZZJH-ROUNDCUBE-SEND-{uuid.uuid4().hex[:12]}"
    compose_payload = {
        "_token": hidden_value(page, "_token"),
        "_task": "mail",
        "_action": "send",
        "_id": hidden_value(page, "_id"),
        "_from": html.unescape(identity_match.group(1)),
        "_to": os.environ["BOB_EMAIL"],
        "_cc": "",
        "_bcc": "",
        "_replyto": "",
        "_followupto": "",
        "_subject": subject,
        "_message": "Roundcube automated send verification",
        "_editor": "0",
        "_priority": "0",
        "_store_target": "",
    }
    session.request(f"{URL}?_task=mail", compose_payload)
    wait_for_delivery(subject)
    print("PASS Roundcube composed message reached Bob's IMAP mailbox")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
