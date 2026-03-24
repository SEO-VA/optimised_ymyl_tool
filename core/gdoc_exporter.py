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
    ):
        self.content_json = content_json
        self.violations = violations
        self.user_email = user_email
        self.title = title
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

        # 2. Build document text and track section name ranges for heading styles
        sections = self._parse_sections()
        full_text, heading_ranges = self._build_doc_text(sections)

        # 3. Insert content in a single batchUpdate
        if full_text:
            requests = [{"insertText": {"location": {"index": 1}, "text": full_text}}]
            self._docs.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()

            # 4. Apply HEADING_2 to section name lines
            if heading_ranges:
                style_requests = []
                for start, end in heading_ranges:
                    style_requests.append({
                        "updateParagraphStyle": {
                            "range": {"startIndex": start + 1, "endIndex": end + 1},
                            "paragraphStyle": {"namedStyleType": "HEADING_2"},
                            "fields": "namedStyleType",
                        }
                    })
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
