#!/usr/bin/env python3
"""
Audit Orchestrator Module
Updated: Added 'Python Safety Net' (_restore_translations) to force translations back 
into the report if the Deduplicator AI drops them.
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

# CONTROL CONCURRENCY
MAX_CONCURRENT_AUDITS = 3

class AuditOrchestrator:
    
    def __init__(self):
        try:
            self.regular_id = st.secrets["regular_assistant_id"]
            self.casino_id = st.secrets["casino_assistant_id"]
            self.dedup_id = st.secrets["deduplicator_assistant_id"]
        except KeyError:
            safe_log("Orchestrator: Missing Assistant IDs in secrets", "CRITICAL")
            raise

    async def run_analysis(self, 
                         content_json: str, 
                         casino_mode: bool, 
                         debug_mode: bool,
                         audit_count: int = 5) -> Dict[str, Any]:
        start_time = time.time()
        target_assistant_id = self.casino_id if casino_mode else self.regular_id
        
        safe_log(f"Orchestrator: Starting {audit_count} audits (Max concurrent: {MAX_CONCURRENT_AUDITS})")

        # --- RATE LIMIT PROTECTION ---
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)

        async def _run_with_semaphore(index):
            async with semaphore:
                await asyncio.sleep(index * 0.5) 
                return await openai_service.get_response_async(
                    content=content_json,
                    assistant_id=target_assistant_id,
                    task_name=f"Audit #{index+1}"
                )

        tasks = [_run_with_semaphore(i) for i in range(audit_count)]
        raw_results = await asyncio.gather(*tasks)
        
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
                "error": f"All {audit_count} audits failed. (Check OpenAI Rate Limits)"
            }

        # Deduplication Logic
        if audit_count > 1:
            unique_violations = await self._run_deduplication(all_violations, content_json)
        else:
            safe_log("Orchestrator: Skipping deduplication (Test Mode)", "INFO")
            unique_violations = all_violations
        
        # Generate Report
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
            "task": "deduplicate_violations_and_merge",
            "IMPORTANT_RULE": "You MUST PRESERVE the 'translation' and 'rewrite_translation' fields for every violation if they exist in the input. Do not drop them.",
            "input_violation_count": len(all_violations),
            "violations": [v.to_dict() for v in all_violations]
        }
        
        success, text, error = await openai_service.get_response_async(
            content=json.dumps(payload, indent=2),
            assistant_id=self.dedup_id,
            task_name="Deduplicator",
            timeout_seconds=400
        )
        
        final_list = []
        if success and text:
            deduped_list = ResponseParser.parse_to_violations(text)
            # --- PYTHON SAFETY NET ---
            # The AI might still drop translations. We forcefully put them back.
            final_list = self._restore_translations(deduped_list, all_violations)
            safe_log(f"Orchestrator: Deduplication complete. {len(all_violations)} -> {len(final_list)}")
        else:
            safe_log("Orchestrator: Deduplication AI failed, returning raw list.", "ERROR")
            final_list = all_violations

        return final_list

    def _restore_translations(self, unique_list: List[Violation], original_list: List[Violation]) -> List[Violation]:
        """
        Looks up the original 'problematic_text' to find translations that the Deduplicator AI dropped.
        """
        # Build a lookup map from the raw data
        # Key: Text snippet -> Value: Translation
        translation_map = {}
        rewrite_map = {}
        
        for v in original_list:
            if v.problematic_text:
                key = v.problematic_text.strip()[:50] # Use first 50 chars as key to handle minor AI edits
                if v.translation:
                    translation_map[key] = v.translation
                if v.rewrite_translation:
                    rewrite_map[key] = v.rewrite_translation
        
        # Restore to unique list
        for v in unique_list:
            if v.problematic_text:
                key = v.problematic_text.strip()[:50]
                
                # Restore Translation
                if not v.translation and key in translation_map:
                    v.translation = translation_map[key]
                
                # Restore Rewrite Translation
                if not v.rewrite_translation and key in rewrite_map:
                    v.rewrite_translation = rewrite_map[key]
                    
        return unique_list

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
                md.append(f"> 🌐 **Translation:** _{v.translation}_")
                
            md.append(f"**Explanation:** {v.explanation}")
            md.append(f"**Guideline:** Section {v.guideline_section} (Page {v.page_number})")
            md.append(f"**Suggested Fix:** \"{v.suggested_rewrite}\"")
            
            if v.rewrite_translation:
                 md.append(f"> 🛠️ **Fix Translation:** _{v.rewrite_translation}_")
            
            md.append("\n---\n")
            count += 1

        md.append(f"\n**Total Violations:** {len(violations)}")
        return "\n".join(md)

async def analyze_content(content: str, casino_mode: bool, debug_mode: bool, audit_count: int = 5) -> Dict[str, Any]:
    orchestrator = AuditOrchestrator()
    return await orchestrator.run_analysis(content, casino_mode, debug_mode, audit_count)
