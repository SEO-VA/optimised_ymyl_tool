#!/usr/bin/env python3
"""
Analysis Processor Module
Centralizes the execution logic for running YMYL audits.
Handles threading and report generation.
"""

import asyncio
import concurrent.futures
from typing import Dict, Any, Optional, Callable
from core.orchestrator import analyze_content
from core.reporter import generate_word_report
from utils.helpers import safe_log

class AnalysisProcessor:
    """
    Handles the orchestration of content analysis.
    Decouples UI from the complex async/threading logic.
    """

    def process_single_file(self, 
                          content: str, 
                          source_description: str, 
                          casino_mode: bool, 
                          debug_mode: bool = False,
                          audit_count: int = 5) -> Dict[str, Any]:
        """
        Run analysis for a single file/URL with configurable audit count.
        """
        # Run async analysis in a thread to be compatible with Streamlit
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(analyze_content(content, casino_mode, debug_mode, audit_count))
            )
            result = future.result(timeout=600) # 10 minute timeout
            
        if not result.get('success'):
            return result

        # Generate Word Report immediately
        try:
            word_bytes = generate_word_report(
                result['report'],
                f"YMYL Report - {source_description}",
                casino_mode
            )
            
            # Attach word bytes to result for easy access
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
                         status_callback: Optional[Callable[[str, str], None]] = None) -> Dict[str, Any]:
        """
        Run parallel analysis on multiple files.
        """
        results = {}
        
        # Helper wrapper to update status and run analysis
        async def _process_item(filename: str, content: str):
            if status_callback:
                status_callback(filename, 'processing')
                
            try:
                # Run the single file logic
                analysis_result = await analyze_content(content, casino_mode, debug_mode, audit_count)
                
                if analysis_result.get('success'):
                    # Generate report
                    word_bytes = generate_word_report(
                        analysis_result['report'],
                        f"YMYL Report - {filename}",
                        casino_mode
                    )
                    analysis_result['word_bytes'] = word_bytes
                    
                    if status_callback:
                        status_callback(filename, 'complete')
                else:
                    if status_callback:
                        status_callback(filename, 'failed')
                        
                return filename, analysis_result
                
            except Exception as e:
                if status_callback:
                    status_callback(filename, 'failed')
                return filename, {'success': False, 'error': str(e)}

        # Run all files in parallel async tasks
        async def _run_batch():
            tasks = []
            for filename, content in files_data.items():
                tasks.append(_process_item(filename, content))
            
            return await asyncio.gather(*tasks)

        # Execute the batch in a thread
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: asyncio.run(_run_batch()))
            batch_results = future.result(timeout=900) # 15 minute timeout for batches
            
        # Convert list of tuples back to dict
        for filename, result in batch_results:
            results[filename] = result
            
        return results

# Global instance for ease of use
processor = AnalysisProcessor()
