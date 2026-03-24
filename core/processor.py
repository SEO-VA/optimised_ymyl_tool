#!/usr/bin/env python3
"""
Analysis Processor Module
"""

import asyncio
import concurrent.futures
import os
from typing import Dict, Any
from core.orchestrator import analyze_content
from core.reporter import generate_word_report
from utils.helpers import safe_log

def _is_mock_enabled() -> bool:
    """Check if mock mode is enabled via Streamlit secrets."""
    import streamlit as st
    return str(st.secrets.get("USE_MOCK_PROCESSOR", "false")).lower() == "true"

class AnalysisProcessor:
    def process_single_file(self, content: str, source_description: str, topic_description: str = "", debug_mode: bool = False, mock_mode: bool = False) -> Dict[str, Any]:
        if mock_mode or _is_mock_enabled():
            from core.mock_processor import mock_processor
            return mock_processor.process_single_file(content, source_description, topic_description, debug_mode)

        # Run async analysis in a thread
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: asyncio.run(analyze_content(content, topic_description, debug_mode)))
            result = future.result(timeout=600)

        if not result.get('success'): return result

        # Generate Report
        try:
            result['word_bytes'] = generate_word_report(result['report'], f"YMYL Report - {source_description}", topic_description)
            return result
        except Exception as e:
            safe_log(f"Report generation failed: {e}")
            result['success'] = False; result['error'] = str(e); return result

    def generate_google_doc(self, content_json: str, violations: list, user_email: str, title: str, report_markdown: str = "") -> str:
        from core.gdoc_exporter import GoogleDocExporter
        exporter = GoogleDocExporter(content_json, violations, user_email, title, report_markdown=report_markdown)
        return exporter.export()

    def process_multi_file(self, *args, **kwargs): pass # Placeholder for multi-file

processor = AnalysisProcessor()
