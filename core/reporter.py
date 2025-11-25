#!/usr/bin/env python3
import asyncio
import concurrent.futures
from typing import Dict, Any
from core.orchestrator import analyze_content
from core.reporter import generate_word_report
from utils.helpers import safe_log

class AnalysisProcessor:
    def process_single_file(self, content: str, source_description: str, casino_mode: bool, debug_mode: bool = False, audit_count: int = 5) -> Dict[str, Any]:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: asyncio.run(analyze_content(content, casino_mode, debug_mode, audit_count)))
            result = future.result(timeout=600)
            
        if not result.get('success'): return result

        try:
            result['word_bytes'] = generate_word_report(result['report'], f"YMYL Report - {source_description}", casino_mode)
            return result
        except Exception as e:
            safe_log(f"Report generation failed: {e}")
            result['success'] = False; result['error'] = str(e); return result

    def process_multi_file(self, *args, **kwargs): pass # Placeholder

processor = AnalysisProcessor()
