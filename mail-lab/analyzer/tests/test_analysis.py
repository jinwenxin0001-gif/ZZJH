"""Unit tests for MIME attachment extraction and analysis headers."""

from __future__ import annotations

import base64
import io
import unittest
import zipfile
from email.message import EmailMessage

from attachment_analyzer.analysis import AttachmentAnalyzer


def zip_payload() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("notice.txt", "ZZJH attachment type test")
    return stream.getvalue()


class AttachmentAnalyzerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = AttachmentAnalyzer()

    def test_detects_zip_disguised_as_pdf(self) -> None:
        message = EmailMessage()
        message["From"] = "alice@zzjh.test"
        message["To"] = "bob@zzjh.test"
        message["Subject"] = "unit test"
        message.set_content("attachment follows")
        message.add_attachment(
            zip_payload(),
            maintype="application",
            subtype="pdf",
            filename="invoice.pdf",
        )

        result = self.analyzer.analyze(message.as_bytes())
        self.assertEqual(result["attachment_count"], 1)
        attachment = result["attachments"][0]
        self.assertEqual(attachment["detected"]["label"], "zip")
        self.assertTrue(attachment["mismatch"])
        self.assertIn("declared_mime", attachment["mismatch_reasons"])
        self.assertIn("filename_extension", attachment["mismatch_reasons"])

    def test_headers_are_added_and_spoofed_headers_removed(self) -> None:
        raw = (
            b"From: alice@zzjh.test\r\n"
            b"To: bob@zzjh.test\r\n"
            b"X-ZZJH-Attachment-Analysis: forged\r\n"
            b"Subject: no attachment\r\n\r\nbody\r\n"
        )
        result = self.analyzer.analyze(raw)
        filtered = self.analyzer.add_result_headers(raw, result)
        self.assertIn(b"X-ZZJH-Attachment-Analysis: v=1; count=0", filtered)
        self.assertNotIn(b"forged", filtered)
        self.assertTrue(filtered.endswith(b"body\r\n"))

    def test_common_correctly_declared_types(self) -> None:
        samples = [
            (
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0l"
                    "EQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                ),
                "image",
                "png",
                "pixel.png",
                "png",
            ),
            (
                b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\n"
                b"endobj\n2 0 obj\n<< /Type /Pages /Count 0 >>\nendobj\n"
                b"xref\n0 3\n0000000000 65535 f \ntrailer\n"
                b"<< /Root 1 0 R /Size 3 >>\nstartxref\n100\n%%EOF\n",
                "application",
                "pdf",
                "report.pdf",
                "pdf",
            ),
            (
                ("高校邮件附件类型识别测试。\n" * 100).encode(),
                "text",
                "plain",
                "notes.txt",
                "txt",
            ),
        ]
        message = EmailMessage()
        message["From"] = "alice@zzjh.test"
        message["To"] = "bob@zzjh.test"
        message.set_content("three attachments")
        for payload, maintype, subtype, filename, _ in samples:
            message.add_attachment(
                payload,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )

        result = self.analyzer.analyze(message.as_bytes())
        self.assertEqual(result["attachment_count"], 3)
        self.assertEqual(result["mismatch_count"], 0)
        self.assertEqual(
            [item["detected"]["label"] for item in result["attachments"]],
            [sample[-1] for sample in samples],
        )


if __name__ == "__main__":
    unittest.main()
