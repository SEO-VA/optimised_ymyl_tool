#!/usr/bin/env python3
"""
Analysis Processor Module
"""

import asyncio
import concurrent.futures
from typing import Dict, Any, Optional, Callable
from core.orchestrator import analyze_content
from core.reporter import generate_word_report
from utils.helpers import safe_log

class AnalysisProcessor:

    def process_single_file(self, 
                          content: str, 
                          source_description: str, 
                          casino_mode: bool, 
                          debug_mode: bool = False,
                          audit_count: int = 5,
                          translate_mode: bool = True) -> Dict[str, Any]: # <--- New Arg
        """
        Run analysis for a single file with translation toggle.
        """
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(analyze_content(content, casino_mode, debug_mode, audit_count, translate_mode))
            )
            result = future.result(timeout=600)
            
        if not result.get('success'):
            return result

        try:
            word_bytes = generate_word_report(
                result['report'],
                f"YMYL Report - {source_description}",
                casino_mode
            )
            result['word_bytes'] = word_bytes
            return result
            
        except Exception as e:
            safe_log(f"Report generation failed: {e}")
            result['success'] = False
            result['error'] = f"Report generation failed: {str(e)}"
            return result

    def process_multi_file(self, 
                         files_data: Dict[str, str], 
                         casino_mode: bool, 
                         debug_mode: bool = False,
                         audit_count: int = 5,
                         translate_mode: bool = True) -> Dict[str, Any]:
        # Implementation would mirror single file but iterate over dict
        pass

processor = AnalysisProcessor()
