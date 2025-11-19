#!/usr/bin/env python3
"""
Audit Orchestrator Module
The Strategy Layer. Coordinates the Multi-Audit Workflow.
Updated to support variable audit counts (Test Mode).
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
    Manages the YMYL Audit Workflow.
    """
    
    def __init__(self):
        try:
            self.regular_id = st.secrets["regular_assistant_id"]
            self.casino_id = st.secrets["casino_assistant_id"]
            self.dedup_id = st.secrets["deduplicator_assistant_id"]
        except KeyError:
            safe_log("Orchestrator: Missing Assistant IDs in secrets", "CRITICAL")
            raise

    # UPDATE 1: Added audit_count parameter here
    async def run_analysis(self, 
                         content_json: str, 
                         casino_mode: bool, 
                         debug_mode: bool,
                         audit_count: int = 5) -> Dict[str, Any]:
        """
        Main entry point.
        Args:
            audit_count: Number of parallel audits to run (Default 5, use 1 for testing)
        """
        start_time = time.time()
        
        # 1. Select Assistant
        target_assistant_id = self.casino_id if casino_mode else self.regular_id
        safe_log(f"Orchestrator: Starting {audit_count} audits (Casino: {casino_mode})")

        # 2. Run Parallel Audits (Dynamic Count)
        # UPDATE 2: Uses audit_count range instead of hardcoded 5
        tasks = [
            openai_service.get_response_async(
                content=content_json,
                assistant_id=target_assistant_id,
                task_name=f"Audit #{i+1}"
            )
            for i in range(audit_count)
        ]
        
        # Wait for all to finish
        raw_results = await asyncio.gather(*tasks)
        
        # 3. Parse Results
        all_violations = []
        successful_audits = 0
        raw_debug_data = []

        for i, (success, text, error) in enumerate(raw_results):
            audit_id = i + 1
            if success and text:
                violations = ResponseParser.parse_to_violations(text)
                
                if violations:
                    successful_audits += 1
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
                "error": f"All {audit_count} AI audits failed to return valid data."
            }

        # 4. Deduplication logic
        unique_violations = await self._run_deduplication(all_violations, content_json)
        
        # 5. Generate Report
        report_md = self._generate_markdown(unique_violations, successful_audits)

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
        if not all_violations: return []

        safe_log(f"Orchestrator: Deduplicating {len(all_violations)} violations...")

        payload = {
            "task": "deduplicate_violations",
            "total_violations_input": len(all_violations),
            "violations": [v.to_dict() for v in all_violations]
        }
        
        payload_json = json.dumps(payload, indent=2)
        
        success, text, error = await openai_service.get_response_async(
            content=payload_json,
            assistant_id=self.dedup_id,
            task_name="Deduplicator",
            timeout_seconds=400
        )
        
        if success and text:
            unique_violations = ResponseParser.parse_to_violations(text)
            if unique_violations:
                return unique_violations
        
        safe_log("Orchestrator: Deduplication AI failed, returning raw list.", "ERROR")
        return all_violations

    def _generate_markdown(self, violations: List[Violation], audit_count: int) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        md = [f"# YMYL Compliance Report\n**Date:** {date_str}\n**Audits Performed:** {audit_count}\n---"]
        
        if not violations:
            md.append("\n✅ **No violations found.**")
            return "\n".join(md)
        
        count = 1
        for v in violations:
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

# UPDATE 3: The bridge function MUST accept the new argument
async def analyze_content(content: str, casino_mode: bool, debug_mode: bool, audit_count: int = 5) -> Dict[str, Any]:
    """
    Bridge function that allows Processor.py to call this new system.
    """
    orchestrator = AuditOrchestrator()
    return await orchestrator.run_analysis(content, casino_mode, debug_mode, audit_count)
