#!/usr/bin/env python3
"""
Mock Processor for Testing
Simulates the audit pipeline without calling OpenAI APIs.
Use for testing the Google Doc export and UI flows.
"""

import json
import time
from typing import Dict, Any, List
from core.models import Violation, Severity, AnalysisResult
from core.reporter import generate_word_report
from utils.helpers import safe_log


class MockAnalysisProcessor:
    """Mock version of AnalysisProcessor for testing."""

    def process_single_file(
        self,
        content: str,
        source_description: str,
        topic_description: str = "",
        debug_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Mock analysis: returns hardcoded violations without calling OpenAI.
        """
        start_time = time.time()
        safe_log(f"MockProcessor: Processing '{source_description}' (mock mode)")

        # Parse sections from content JSON
        sections = self._parse_sections(content)

        # Generate mock violations from content
        violations = self._generate_mock_violations(sections, content)

        # Build markdown report
        report = self._generate_markdown(violations)

        # Generate Word report
        word_bytes = generate_word_report(report, f"YMYL Report - {source_description}", topic_description)

        processing_time = time.time() - start_time

        return {
            "success": True,
            "report": report,
            "violations": violations,
            "word_bytes": word_bytes,
            "processing_time": processing_time,
            "total_violations_found": len(violations),
            "unique_violations": len(violations),
            "debug_info": None,
        }

    def generate_google_doc(self, content_json: str, violations: List[Violation], user_email: str, title: str) -> str:
        """Delegate to real Google Doc exporter."""
        from core.gdoc_exporter import GoogleDocExporter
        exporter = GoogleDocExporter(content_json, violations, user_email, title)
        return exporter.export()

    def _parse_sections(self, content: str) -> list:
        try:
            data = json.loads(content)
            return data.get("sections", [])
        except Exception:
            return []

    def _generate_mock_violations(self, sections: list, content: str) -> List[Violation]:
        """
        Generate mock violations by scanning content for common YMYL keywords.
        This simulates what the AI audit would find.
        """
        violations = []

        # Keywords to scan for (simulates detection logic)
        keyword_violations = {
            "guaranteed": {
                "type": "Misleading Financial Claim",
                "severity": Severity.CRITICAL,
                "explanation": "Content uses 'guaranteed' language which implies assured returns, violating YMYL guidelines on financial promises.",
                "section": "3.2",
                "suggestion": 'Change "guaranteed returns" to "potential returns" or "historical performance"',
            },
            "risk-free": {
                "type": "Misleading Safety Claim",
                "severity": Severity.HIGH,
                "explanation": "Claims about risk-free investments violate YMYL standards. All investments carry risk.",
                "section": "3.1",
                "suggestion": 'Remove "risk-free" language. Disclose actual risks involved.',
            },
            "doctor approved": {
                "type": "Unsubstantiated Medical Claim",
                "severity": Severity.CRITICAL,
                "explanation": "Generic medical claims without specific evidence. YMYL requires medical content to cite authoritative sources.",
                "section": "4.1",
                "suggestion": "Link to peer-reviewed studies or FDA-approved sources.",
            },
            "lose weight fast": {
                "type": "Misleading Health Claim",
                "severity": Severity.HIGH,
                "explanation": "Unrealistic weight loss promises. YMYL requires realistic health expectations.",
                "section": "4.2",
                "suggestion": 'Replace with evidence-based weight loss information and realistic timelines.',
            },
            "earn $10,000": {
                "type": "Unrealistic Income Promise",
                "severity": Severity.HIGH,
                "explanation": "Unsubstantiated income claims. YMYL requires disclosure of typical earnings.",
                "section": "3.3",
                "suggestion": "Add disclaimers: 'Results may vary. See earnings disclosures.'",
            },
        }

        # Scan content for keywords
        content_lower = content.lower()
        found_keywords = set()

        for keyword, violation_data in keyword_violations.items():
            if keyword in content_lower:
                found_keywords.add(keyword)

        # Extract sample problematic text from sections
        page_num = 1
        for idx, section in enumerate(sections):
            section_name = section.get("name", "").lower()
            section_content = section.get("content", "").lower()
            full_section = f"{section_name} {section_content}"

            for keyword in found_keywords:
                if keyword in full_section:
                    # Find the actual snippet in original content
                    orig_content = section.get("content", "")
                    if keyword.title() in orig_content:
                        snippet = keyword.title()
                    elif keyword.upper() in orig_content:
                        snippet = keyword.upper()
                    else:
                        snippet = keyword

                    v_data = keyword_violations[keyword]
                    violations.append(
                        Violation(
                            problematic_text=snippet,
                            violation_type=v_data["type"],
                            explanation=v_data["explanation"],
                            guideline_section=v_data["section"],
                            page_number=page_num,
                            severity=v_data["severity"],
                            suggested_rewrite=v_data["suggestion"],
                            translation=None,
                            rewrite_translation=None,
                            chunk_language="English",
                        )
                    )

            page_num += 1

        # If no violations found, add a sample one for testing
        if not violations:
            violations.append(
                Violation(
                    problematic_text="This is a test violation",
                    violation_type="Sample Compliance Issue",
                    explanation="This is a mock violation generated for testing purposes.",
                    guideline_section="1.0",
                    page_number=1,
                    severity=Severity.MEDIUM,
                    suggested_rewrite="Update content to comply with YMYL guidelines.",
                    translation=None,
                    rewrite_translation=None,
                    chunk_language="English",
                )
            )

        return violations

    def _generate_markdown(self, violations: List[Violation]) -> str:
        """Generate markdown report from violations."""
        from datetime import datetime

        date_str = datetime.now().strftime("%Y-%m-%d")
        md = [f"# YMYL Compliance Report (Mock)\n**Date:** {date_str}\n---"]

        if not violations:
            md.append("\n✅ **No violations found.")
            return "\n".join(md)

        count = 1
        for v in violations:
            emoji = "🔴" if v.severity == Severity.CRITICAL else "🟠" if v.severity in [Severity.HIGH, Severity.MEDIUM] else "🔵"

            md.append(f"### {count}. {emoji} {v.violation_type}")
            md.append(f"**Severity:** {v.severity.value.title()}")
            md.append(f"**Problematic Text:** \"{v.problematic_text}\"")
            if v.translation:
                md.append(f"> 🌐 **Translation:** _{v.translation}_")
            md.append(f"**Explanation:** {v.explanation}")
            md.append(f"**Guideline:** Section {v.guideline_section} (Page {v.page_number})")
            md.append(f"**Suggested Fix:** \"{v.suggested_rewrite}\"")
            if v.rewrite_translation:
                md.append(f"> 🛠️ **Fix Translation:** _{v.rewrite_translation}_")
            md.append("\n---\n")
            count += 1

        return "\n".join(md)


# Global mock processor instance
mock_processor = MockAnalysisProcessor()
