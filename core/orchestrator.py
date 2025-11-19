#!/usr/bin/env python3
"""
Audit Orchestrator Module
The Strategy Layer. Coordinates the "5-Audit" workflow.
1. Sends content to 5 parallel AI assistants.
2. Aggregates and parses their responses.
3. Sends combined data to a Deduplicator AI.
4. Generates the final AnalysisResult.
"""

import asyncio
import json
import time
import streamlit as st
from typing import List, Dict, Any
from datetime import datetime

from core.models import AnalysisResult, Violation
from core.service import openai_service
from core.parser import ResponseParser
from utils.helpers import safe_log

class AuditOrchestrator:
    """
    Managers the YMYL 5-Audit Workflow.
    """
    
    def __init__(self):
        # Load configuration from secrets (Standard Streamlit way)
        try:
            self.regular_id = st.secrets["regular_assistant_id"]
            self.casino_id = st.secrets["casino_assistant_id"]
            self.dedup_id = st.secrets["deduplicator_assistant_id"]
        except KeyError:
            safe_log("Orchestrator: Missing Assistant IDs in secrets", "CRITICAL")
            raise

    async def run_analysis(self, content_json: str, casino_mode: bool, debug_mode: bool) -> Dict[str, Any]:
        """
        Main entry point for the logic.
        Returns a Dictionary compatible with AnalysisResult model.
        """
        start_time = time.time()
        
        # 1. Select Assistant
        target_assistant_id = self.casino_id if casino_mode else self.regular_id
        safe_log(f"Orchestrator: Starting 5 audits (Casino: {casino_mode})")

        # 2. Run 5 Parallel Audits
        # We create 5 identical tasks
        tasks = [
            openai_service.get_response_async(
                content=content_json,
                assistant_id=target_assistant_id,
                task_name=f"Audit #{i+1}"
            )
            for i in range(5)
        ]
        
        # Wait for all 5 to finish
        raw_results = await asyncio.gather(*tasks)
        
        # 3. Parse Results
        all_violations = []
        successful_audits = 0
        raw_debug_data = [] # For Admin Debug Mode

        for i, (success, text, error) in enumerate(raw_results):
            audit_id = i + 1
            if success and text:
                # Use our new Parser to fix quotes and map to objects
                violations = ResponseParser.parse_to_violations(text)
                
                if violations:
                    successful_audits += 1
                    # Tag violations with their source audit ID
                    for v in violations:
                        v.source_audit_id = audit_id
                        all_violations.append(v)
                
                if debug_mode:
                    raw_debug_data.append({
                        "audit_number": audit_id,
                        "raw_response": text,
                        "parsed_count": len(violations)
                    })
            else:
                safe_log(f"Audit #{audit_id} failed: {error}", "WARNING")

        if successful_audits == 0:
            return {
                "success": False, 
                "error": "All 5 AI audits failed to return valid data."
            }

        # 4. Deduplication (The Merge Strategy)
        # We re-group violations by chunk to send to the Deduplicator AI
        unique_violations = await self._run_deduplication(all_violations, content_json)
        
        # 5. Generate Report Markdown
        report_md = self._generate_markdown(unique_violations, successful_audits)

        # 6. Return Final Result
        processing_time = time.time() - start_time
        
        return {
            "success": True,
            "report": report_md,
            "violations": unique_violations,
            "processing_time": processing_time,
            "total_violations_found": len(all_violations),
            "unique_violations": len(unique_violations),
            "debug_info": raw_debug_data if debug_mode else None,
            "debug_mode": debug_mode
        }

    async def _run_deduplication(self, all_violations: List[Violation], original_content_json: str) -> List[Violation]:
        """
        Sends collected violations to the Deduplicator AI to remove redundancies.
        """
        if not all_violations:
            return []

        safe_log(f"Orchestrator: Deduplicating {len(all_violations)} violations...")

        # Prepare payload for Deduplicator
        # We convert Violations back to dicts for the AI to read
        payload = {
            "task": "deduplicate_violations",
            "total_violations_input": len(all_violations),
            "violations": [v.to_dict() for v in all_violations]
        }
        
        payload_json = json.dumps(payload, indent=2)
        
        # Call OpenAI Service (Deduplicator ID)
        success, text, error = await openai_service.get_response_async(
            content=payload_json,
            assistant_id=self.dedup_id,
            task_name="Deduplicator",
            timeout_seconds=400 # Deduplication can take time
        )
        
        if success and text:
            # Parse the cleaned list back into objects
            unique_violations = ResponseParser.parse_to_violations(text)
            if unique_violations:
                safe_log(f"Orchestrator: Deduplication complete. {len(all_violations)} -> {len(unique_violations)}")
                return unique_violations
        
        # Fallback: If Deduplicator fails, return all violations (better than nothing)
        safe_log("Orchestrator: Deduplication AI failed, returning raw list.", "ERROR")
        return all_violations

    def _generate_markdown(self, violations: List[Violation], audit_count: int) -> str:
        """
        Generates the final Markdown report from Violation objects.
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        md = [f"# YMYL Compliance Multi-Audit Report\n**Date:** {date_str}\n**Audits Performed:** {audit_count}\n---"]
        
        if not violations:
            md.append("\n✅ **No violations found across all audits.**")
            return "\n".join(md)

        # Group by "Content Name" or Chunk (Logic simplified for brevity)
        # We simply list them since Violation object contains section info
        
        count = 1
        for v in violations:
            # Map severity enum to Emoji
            emoji = "🟡"
            if v.severity.value == "critical": emoji = "🔴"
            elif v.severity.value == "high": emoji = "🟠"
            elif v.severity.value == "low": emoji = "🔵"

            md.append(f"### {count}. {emoji} {v.violation_type}")
            md.append(f"**Severity:** {v.severity.value.title()}")
            md.append(f"**Problematic Text:** \"{v.problematic_text}\"")
            if v.translation:
                md.append(f"**Translation:** \"{v.translation}\"")
                
            md.append(f"**Explanation:** {v.explanation}")
            md.append(f"**Guideline:** Section {v.guideline_section} (Page {v.page_number})")
            md.append(f"**Suggested Fix:** \"{v.suggested_rewrite}\"")
            
            md.append("\n---\n")
            count += 1

        md.append(f"\n**Total Violations:** {len(violations)}")
        return "\n".join(md)

# Compatibility Wrapper for Processor.py
async def analyze_content(content: str, casino_mode: bool, debug_mode: bool) -> Dict[str, Any]:
    """
    Bridge function that allows Processor.py to call this new system 
    without changing its code.
    """
    orchestrator = AuditOrchestrator()
    return await orchestrator.run_analysis(content, casino_mode, debug_mode)
