"""MIME attachment extraction and Magika content-type identification."""

from __future__ import annotations

import hashlib
import importlib.metadata
import re
import threading
import uuid
from dataclasses import dataclass
from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import PurePath
from typing import Any

import onnxruntime as ort
from magika import Magika


GENERIC_MIME_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
    "application/unknown",
}
INTERNAL_HEADER_PREFIX = b"x-zzjh-attachment-"
TRACE_HEADER = b"x-zzjh-trace-id"


@dataclass(frozen=True)
class AnalysisConfig:
    """Resource limits for a single message."""

    max_attachments: int = 100
    max_attachment_bytes: int = 25 * 1024 * 1024
    inference_threads: int = 2


class BoundedMagika(Magika):
    """Pinned Magika adapter with explicit ONNX CPU thread limits."""

    def __init__(self, inference_threads: int) -> None:
        self._inference_threads = inference_threads
        super().__init__()

    def _init_onnx_session(self) -> ort.InferenceSession:
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.intra_op_num_threads = self._inference_threads
        options.inter_op_num_threads = 1
        return ort.InferenceSession(
            self._model_path,
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )


class AttachmentAnalyzer:
    """Analyze top-level MIME attachments without trusting names or MIME headers."""

    def __init__(self, config: AnalysisConfig | None = None) -> None:
        self.config = config or AnalysisConfig()
        self._magika = BoundedMagika(self.config.inference_threads)
        self._model_lock = threading.Lock()
        self.model_name = str(self._magika.get_model_name())
        self.module_version = importlib.metadata.version("magika")

    def analyze(self, raw_message: bytes) -> dict[str, Any]:
        """Return a JSON-serializable message and attachment analysis record."""
        message = BytesParser(policy=policy.default).parsebytes(raw_message)
        trace_id = uuid.uuid4().hex
        attachment_parts = list(self._attachment_parts(message))
        if len(attachment_parts) > self.config.max_attachments:
            raise ValueError(
                "attachment count exceeds limit: "
                f"{len(attachment_parts)} > {self.config.max_attachments}"
            )

        attachments: list[dict[str, Any]] = []
        for index, part in enumerate(attachment_parts, start=1):
            attachments.append(self._analyze_part(index, part))

        mismatch_count = sum(bool(item["mismatch"]) for item in attachments)
        error_count = sum(item["status"] != "ok" for item in attachments)
        return {
            "schema_version": 1,
            "trace_id": trace_id,
            "message_id": self._safe_header(message.get("Message-ID")),
            "subject": self._safe_header(message.get("Subject"), limit=300),
            "model": {
                "name": self.model_name,
                "magika_version": self.module_version,
            },
            "attachment_count": len(attachments),
            "mismatch_count": mismatch_count,
            "error_count": error_count,
            "attachments": attachments,
        }

    def add_result_headers(self, raw_message: bytes, result: dict[str, Any]) -> bytes:
        """Prepend trusted analysis headers while preserving original MIME body bytes."""
        separator, header_block, body = self._split_message(raw_message)
        cleaned_headers = self._strip_internal_headers(header_block)
        summary = (
            "v=1; "
            f"count={result['attachment_count']}; "
            f"mismatch={result['mismatch_count']}; "
            f"errors={result['error_count']}; "
            f"model={result['model']['name']}"
        )
        type_items = []
        for item in result["attachments"]:
            label = item.get("detected", {}).get("label", "error")
            score = item.get("detected", {}).get("score")
            score_text = f"{score:.3f}" if isinstance(score, float) else "na"
            state = "mismatch" if item["mismatch"] else item["status"]
            type_items.append(f"{item['index']}={label}/{score_text}/{state}")
        type_summary = ",".join(type_items) if type_items else "none"
        type_summary = type_summary[:900]

        newline = b"\r\n" if separator == b"\r\n\r\n" else b"\n"
        added = newline.join(
            [
                b"X-ZZJH-Trace-ID: " + result["trace_id"].encode("ascii"),
                b"X-ZZJH-Attachment-Analysis: " + summary.encode("ascii"),
                b"X-ZZJH-Attachment-Types: " + type_summary.encode("ascii"),
            ]
        )
        return added + newline + cleaned_headers + separator + body

    def _analyze_part(self, index: int, part: Message) -> dict[str, Any]:
        filename = self._safe_filename(part.get_filename())
        declared_mime = part.get_content_type().lower()
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""
        size = len(payload)
        extension = self._filename_extension(filename)
        base: dict[str, Any] = {
            "index": index,
            "filename": filename,
            "size_bytes": size,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "declared": {
                "mime_type": declared_mime,
                "extension": extension,
            },
            "status": "ok",
            "mismatch": False,
            "mismatch_reasons": [],
        }

        if size > self.config.max_attachment_bytes:
            base["status"] = "skipped_size_limit"
            base["mismatch"] = False
            base["error"] = (
                f"attachment exceeds {self.config.max_attachment_bytes} byte limit"
            )
            return base

        try:
            with self._model_lock:
                magika_result = self._magika.identify_bytes(payload)
            if not magika_result.ok:
                raise RuntimeError(str(magika_result.status))
            output = magika_result.output
            extensions = sorted(str(value).lower() for value in output.extensions)
            detected = {
                "label": str(output.label),
                "mime_type": str(output.mime_type).lower(),
                "description": str(output.description),
                "group": str(output.group),
                "is_text": bool(output.is_text),
                "extensions": extensions,
                "score": float(magika_result.score),
            }
            base["detected"] = detected

            if (
                declared_mime not in GENERIC_MIME_TYPES
                and declared_mime != detected["mime_type"]
            ):
                base["mismatch_reasons"].append("declared_mime")
            if extension and extensions and extension not in extensions:
                base["mismatch_reasons"].append("filename_extension")
            base["mismatch"] = bool(base["mismatch_reasons"])
            return base
        except Exception as exc:
            base["status"] = "analysis_error"
            base["error"] = f"{type(exc).__name__}: {exc}"[:500]
            return base

    @staticmethod
    def _attachment_parts(message: Message):
        for part in message.walk():
            if part.is_multipart():
                continue
            if part.get_content_disposition() == "attachment" or part.get_filename():
                yield part

    @staticmethod
    def _safe_header(value: object | None, limit: int = 500) -> str | None:
        if value is None:
            return None
        text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()
        return text[:limit]

    @classmethod
    def _safe_filename(cls, value: object | None) -> str:
        return cls._safe_header(value, limit=255) or "unnamed"

    @staticmethod
    def _filename_extension(filename: str) -> str | None:
        suffix = PurePath(filename).suffix.lower().lstrip(".")
        return suffix or None

    @staticmethod
    def _split_message(raw_message: bytes) -> tuple[bytes, bytes, bytes]:
        for separator in (b"\r\n\r\n", b"\n\n"):
            position = raw_message.find(separator)
            if position >= 0:
                return (
                    separator,
                    raw_message[:position],
                    raw_message[position + len(separator) :],
                )
        raise ValueError("message has no header/body separator")

    @staticmethod
    def _strip_internal_headers(header_block: bytes) -> bytes:
        lines = header_block.splitlines(keepends=True)
        retained: list[bytes] = []
        dropping = False
        for line in lines:
            if line[:1] in (b" ", b"\t"):
                if not dropping:
                    retained.append(line)
                continue
            name, delimiter, _ = line.partition(b":")
            lowered = name.strip().lower()
            dropping = bool(delimiter) and (
                lowered.startswith(INTERNAL_HEADER_PREFIX)
                or lowered == TRACE_HEADER
            )
            if not dropping:
                retained.append(line)
        return b"".join(retained)
