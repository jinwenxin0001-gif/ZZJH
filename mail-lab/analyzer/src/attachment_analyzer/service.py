"""SMTP after-queue filter service for attachment content-type analysis."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import smtplib
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiosmtpd.controller import Controller

from .analysis import AnalysisConfig, AttachmentAnalyzer


LOG = logging.getLogger("zzjh.attachment_analyzer")


def env_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


class JsonlResultStore:
    """Append one compact JSON object per analyzed message."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, result: dict[str, Any]) -> None:
        line = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(line)
            stream.write("\n")
            stream.flush()


class FilterHandler:
    """Analyze SMTP DATA content, persist metadata, and re-inject the message."""

    def __init__(
        self,
        analyzer: AttachmentAnalyzer,
        store: JsonlResultStore,
        reinject_host: str,
        reinject_port: int,
        reinject_timeout: int,
    ) -> None:
        self.analyzer = analyzer
        self.store = store
        self.reinject_host = reinject_host
        self.reinject_port = reinject_port
        self.reinject_timeout = reinject_timeout

    async def handle_DATA(self, server, session, envelope):  # noqa: N802
        try:
            response = await asyncio.to_thread(
                self._process_and_reinject, session, envelope
            )
            return response
        except Exception:
            LOG.exception("attachment analysis or re-injection failed")
            return "451 4.3.0 attachment analysis temporarily unavailable"

    def _process_and_reinject(self, session, envelope) -> str:
        raw_message = envelope.original_content or envelope.content
        if not isinstance(raw_message, bytes):
            raise TypeError("SMTP server did not provide raw message bytes")

        result = self.analyzer.analyze(raw_message)
        result["analyzed_at"] = datetime.now(UTC).isoformat()
        result["envelope"] = {
            "mail_from": envelope.mail_from,
            "rcpt_tos": list(envelope.rcpt_tos),
        }
        result["smtp_client"] = {
            "host_name": getattr(session, "host_name", None),
            "peer": list(session.peer) if session.peer else None,
        }
        if result["error_count"]:
            raise RuntimeError(
                f"{result['error_count']} attachment(s) could not be analyzed"
            )
        filtered_message = self.analyzer.add_result_headers(raw_message, result)

        # Persist analysis before re-injection so a storage failure cannot turn
        # a successfully re-injected message into a duplicate on SMTP retry.
        result["status"] = "analysis_complete"
        self.store.append(result)

        with smtplib.SMTP(
            self.reinject_host,
            self.reinject_port,
            timeout=self.reinject_timeout,
        ) as client:
            client.ehlo_or_helo_if_needed()
            refused = client.sendmail(
                envelope.mail_from,
                envelope.rcpt_tos,
                filtered_message,
            )
            if refused:
                raise RuntimeError(f"re-injection refused recipients: {refused}")

        LOG.info(
            "trace_id=%s attachments=%d mismatches=%d errors=%d",
            result["trace_id"],
            result["attachment_count"],
            result["mismatch_count"],
            result["error_count"],
        )
        return f"250 2.0.0 analyzed trace_id={result['trace_id']}"


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("mail.log").setLevel(logging.WARNING)
    listen_host = os.environ.get("ANALYZER_LISTEN_HOST", "0.0.0.0")
    listen_port = env_int("ANALYZER_LISTEN_PORT", 10025)
    data_size_limit = env_int("ANALYZER_MAX_MESSAGE_BYTES", 30 * 1024 * 1024)
    analyzer = AttachmentAnalyzer(
        AnalysisConfig(
            max_attachments=env_int("ANALYZER_MAX_ATTACHMENTS", 100),
            max_attachment_bytes=env_int(
                "ANALYZER_MAX_ATTACHMENT_BYTES", 25 * 1024 * 1024
            ),
            inference_threads=env_int("ANALYZER_INFERENCE_THREADS", 2),
        )
    )
    store = JsonlResultStore(
        Path(
            os.environ.get(
                "ANALYZER_RESULTS_PATH",
                "/data/results/attachment-analysis.jsonl",
            )
        )
    )
    handler = FilterHandler(
        analyzer=analyzer,
        store=store,
        reinject_host=os.environ.get("REINJECT_HOST", "mailserver"),
        reinject_port=env_int("REINJECT_PORT", 10026),
        reinject_timeout=env_int("REINJECT_TIMEOUT_SECONDS", 30),
    )
    controller = Controller(
        handler,
        hostname=listen_host,
        port=listen_port,
        ready_timeout=30,
        data_size_limit=data_size_limit,
        decode_data=False,
        enable_SMTPUTF8=True,
    )
    stopped = threading.Event()

    def stop_handler(signum, frame) -> None:
        del frame
        LOG.info("received signal %s; stopping", signum)
        stopped.set()

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    controller.start()
    LOG.info(
        "ready host=%s port=%d magika_version=%s model=%s",
        listen_host,
        listen_port,
        analyzer.module_version,
        analyzer.model_name,
    )
    try:
        stopped.wait()
    finally:
        controller.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
