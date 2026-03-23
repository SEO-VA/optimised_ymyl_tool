#!/usr/bin/env python3
"""
Analysis Processor Module
"""

import asyncio
import concurrent.futures
from typing import Dict, Any
from core.orchestrator import analyze_content
from core.reporter import generate_word_report
from utils.helpers import safe_log

class AnalysisProcessor:
    def process_single_file(self, content: str, source_description: str, topic_description: str = "", debug_mode: bool = False) -> Dict[str, Any]:
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

    def generate_google_doc(self, content_json: str, violations: list, user_email: str, title: str) -> str:
        from core.gdoc_exporter import GoogleDocExporter
        exporter = GoogleDocExporter(content_json, violations, user_email, title)
        return exporter.export()

    def process_multi_file(self, *args, **kwargs): pass # Placeholder for multi-file

processor = AnalysisProcessor()
