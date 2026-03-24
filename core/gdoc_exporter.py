#!/usr/bin/env python3
"""
Google Doc Exporter
Creates a Google Doc from the original content JSON, then adds inline
comments anchored to each violation's problematic text via the Drive API.
Uses OAuth2 user credentials from core.google_oauth (no service account needed).
"""

import json
from typing import List, Optional
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.models import Violation
from utils.helpers import safe_log

_SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟠",
    "low": "🔵",
}


class GoogleDocExporter:
    def __init__(
        self,
        content_json: str,
        violations: List[Violation],
        user_email: str,
        title: str,
        report_markdown: str = "",
    ):
        self.content_json = content_json
        self.violations = violations
        self.user_email = user_email
        self.title = title
        self.report_markdown = report_markdown
        self._docs = None
        self._drive = None

    def _build_clients(self):
        from core.google_oauth import get_credentials
        creds = get_credentials(self.user_email)
        if not creds:
            raise ValueError("Google Drive not authorized. Please authorize first.")
        self._docs = build("docs", "v1", credentials=creds)
        self._drive = build("drive", "v3", credentials=creds)

    def export(self) -> str:
        """Create Google Doc, insert content, add comments, share. Returns URL."""
        self._build_clients()

        # 1. Create empty document
        doc = self._docs.documents().create(body={"title": self.title}).execute()
        doc_id = doc["documentId"]
        safe_log(f"GDocExporter: Created document {doc_id}")

        if self.report_markdown:
            full_text, heading_ranges, bold_ranges = self._build_report_text()
        else:
            sections = self._parse_sections()
            full_text, raw_ranges = self._build_doc_text(sections)
            heading_ranges = [(start, end, "HEADING_2") for start, end in raw_ranges]
            bold_ranges = []

        if full_text:
            self._docs.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": full_text}}]},
            ).execute()

            style_requests = []
            for start, end, style in heading_ranges:
                style_requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": start + 1, "endIndex": end + 1},
                        "paragraphStyle": {"namedStyleType": style},
                        "fields": "namedStyleType",
                    }
                })
            for start, end in bold_ranges:
                style_requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": start + 1, "endIndex": end + 1},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                })
            if style_requests:
                self._docs.documents().batchUpdate(
                    documentId=doc_id, body={"requests": style_requests}
                ).execute()

        # 5. Add inline comments for each violation
        for v in self.violations:
            if "no violation" in v.violation_type.lower():
                continue
            self._add_comment(doc_id, v, full_text)

        url = f"https://docs.google.com/document/d/{doc_id}/edit"
        safe_log(f"GDocExporter: Done — {url}")
        return url

    def _parse_sections(self) -> list:
        try:
            data = json.loads(self.content_json)
            return data.get("sections", [])
        except Exception:
            return []

    def _build_doc_text(self, sections: list):
        """
        Returns (full_text, heading_ranges).
        heading_ranges: list of (start_char_index, end_char_index) for each section name.
        Indices are 0-based into full_text; we add 1 when sending to the Docs API (which starts at 1).
        """
        parts = []
        heading_ranges = []
        pos = 0

        for section in sections:
            name = (section.get("name") or "").strip()
            content = (section.get("content") or "").strip()

            if name:
                start = pos
                parts.append(name + "\n")
                pos += len(name) + 1
                heading_ranges.append((start, pos - 1))  # exclude the newline

            if content:
                parts.append(content + "\n\n")
                pos += len(content) + 2

        return "".join(parts), heading_ranges

    def _build_report_text(self):
        parts = []
        heading_ranges = []
        bold_ranges = []
        pos = 0

        for raw_line in self.report_markdown.splitlines():
            stripped = raw_line.strip()

            if stripped == "---":
                parts.append("\n")
                pos += 1
                continue

            if stripped.startswith("# "):
                text = stripped[2:]
                start = pos
                parts.append(text + "\n")
                pos += len(text) + 1
                heading_ranges.append((start, pos - 1, "HEADING_1"))
                continue

            if stripped.startswith("### "):
                text = stripped[4:]
                start = pos
                parts.append(text + "\n")
                pos += len(text) + 1
                heading_ranges.append((start, pos - 1, "HEADING_3"))
                continue

            line = stripped[2:] if stripped.startswith("> ") else stripped
            plain_line = []
            line_pos = pos
            index = 0

            while index < len(line):
                if line.startswith("**", index):
                    end = line.find("**", index + 2)
                    if end != -1:
                        text = line[index + 2:end]
                        start = line_pos + len("".join(plain_line))
                        plain_line.append(text)
                        bold_ranges.append((start, start + len(text)))
                        index = end + 2
                        continue
                if line.startswith("_", index):
                    end = line.find("_", index + 1)
                    if end != -1:
                        plain_line.append(line[index + 1:end])
                        index = end + 1
                        continue
                plain_line.append(line[index])
                index += 1

            text = "".join(plain_line)
            parts.append(text + "\n")
            pos += len(text) + 1

        return "".join(parts), heading_ranges, bold_ranges

    def _add_comment(self, doc_id: str, v: Violation, full_text: str):
        """Add a Drive API comment anchored to v.problematic_text."""
        anchor_text = v.problematic_text.strip()

        # Build comment body
        emoji = _SEVERITY_EMOJI.get(v.severity.value, "⚠️")
        lines = [
            f"{emoji} [{v.severity.value.upper()}] {v.violation_type}",
            "",
            v.explanation,
            "",
            f"Guideline: Section {v.guideline_section} (Page {v.page_number})",
            f'Suggested fix: "{v.suggested_rewrite}"',
        ]
        if v.translation:
            lines += ["", f"Translation: {v.translation}"]
        if v.rewrite_translation:
            lines += [f"Fix translation: {v.rewrite_translation}"]
        comment_body = "\n".join(lines)

        # Build comment payload (all comments are unanchored for now — simpler approach)
        comment_payload = {
            "content": f'**Problematic text:** "{anchor_text}"\n\n{comment_body}'
        }

        try:
            self._drive.comments().create(
                fileId=doc_id,
                fields="id",
                body=comment_payload,
            ).execute()
            safe_log(f"GDocExporter: Added comment for '{anchor_text[:50]}...'")
        except HttpError as e:
            safe_log(f"GDocExporter: Comment creation failed: {e}", "WARNING")
        except Exception as e:
            safe_log(f"GDocExporter: Unexpected error adding comment: {e}", "WARNING")
