#!/usr/bin/env python3
"""
Audit Orchestrator Module
The Strategy Layer. Coordinates the "Strict Audit -> Smart Filter" Workflow.
Updated: Always runs Agent 2 (Filter) to apply Critic Defense, even for single audits.
"""

import asyncio
import json
import time
import re
import streamlit as st
from typing import List, Dict, Any, Tuple
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
            self.settings = {
                'regular_assistant_id': st.secrets["regular_assistant_id"],
                'casino_assistant_id': st.secrets["casino_assistant_id"],
                'deduplicator_assistant_id': st.secrets["deduplicator_assistant_id"]
            }
        except KeyError:
            safe_log("Orchestrator: Missing Assistant IDs in secrets", "CRITICAL")
            raise

    async def run_analysis(self, 
                         content_json: str, 
                         casino_mode: bool, 
                         debug_mode: bool,
                         audit_count: int = 5) -> Dict[str, Any]:
        start_time = time.time()
        # Agent 1: The Strict Auditor
        target_assistant_id = self.settings['casino_assistant_id'] if casino_mode else self.settings['regular_assistant_id']
        
        safe_log(f"Orchestrator: Phase 1 - Strict Audit ({audit_count} agents)")

        # 1. Run Strict Audits
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)
        async def _run_audit(index):
            async with semaphore:
                await asyncio.sleep(index * 0.5)
                return await openai_service.get_response_async(
                    content=content_json,
                    assistant_id=target_assistant_id,
                    task_name=f"Strict Auditor #{index+1}"
                )

        raw_results = await asyncio.gather(*[_run_audit(i) for i in range(audit_count)])
        
        all_violations = []
        successful_audits = 0
        raw_debug_data = []

        for i, (success, text, error) in enumerate(raw_results):
            if success and text:
                violations = ResponseParser.parse_to_violations(text)
                # Fix: Accept empty list as valid success
                if isinstance(violations, list):
                    successful_audits += 1
                    for v in violations:
                        v.source_audit_id = i + 1
                    all_violations.extend(violations)
                
                if debug_mode:
                    raw_debug_data.append({
                        "audit_number": i + 1,
                        "raw_response": text,
                        "parsed_count": len(violations) if violations else 0
                    })

        if successful_audits == 0:
            return {"success": False, "error": "All audits failed."}

        # 2. Phase 2: The Smart Filter (Deduplicator)
        # We MUST run this to apply the "Critic Defense" filter, even for 1 audit
        safe_log("Orchestrator: Phase 2 - Smart Filter & Deduplication")
        
        # Extract just the backpack (Chunk 0) to pass to Agent 2
        backpack_context = "Global Context Not Found"
        try:
            data = json.loads(content_json)
            if data.get("big_chunks") and data["big_chunks"][0]["big_chunk_index"] == 0:
                backpack_context = json.dumps(data["big_chunks"][0])
        except: pass

        final_violations, filter_raw_text = await self._run_smart_filter(
            all_violations, 
            backpack_context
        )
        
        # 3. Generate Report
        report_md = self._generate_markdown(final_violations, successful_audits)
        
        # 4. Debug Package
        debug_package = None
        if debug_mode:
            debug_package = {
                "audits": raw_debug_data,
                "filter_raw": filter_raw_text,
                "input_count": len(all_violations),
                "final_count": len(final_violations)
            }

        return {
            "success": True,
            "report": report_md,
            "violations": final_violations,
            "processing_time": time.time() - start_time,
            "total_violations_found": len(all_violations),
            "unique_violations": len(final_violations),
            "debug_info": debug_package,
            "debug_mode": debug_mode,
            "word_bytes": None
        }

    async def _run_smart_filter(self, violations: List[Violation], context_backpack: str) -> Tuple[List[Violation], str]:
        # If Agent 1 found nothing, we have nothing to filter
        if not violations: return [], "Skipped (No violations found)"

        # Payload for Agent 2
        payload = {
            "task": "filter_and_deduplicate",
            "context_backpack": context_backpack,
            "instructions": [
                "1. APPLY CRITIC DEFENSE: Remove violations that are honest critiques (e.g. 'No FAQ found').",
                "2. MERGE DUPLICATES: Combine similar issues.",
                "3. PRESERVE TRANSLATIONS: Do not delete 'translation' fields."
            ],
            "violations_to_review": [v.to_dict() for v in violations]
        }
        
        success, text, error = await openai_service.get_response_async(
            content=json.dumps(payload, indent=2),
            assistant_id=self.settings['deduplicator_assistant_id'],
            task_name="Smart Filter",
            timeout_seconds=400
        )
        
        if success and text:
            filtered_list = ResponseParser.parse_to_violations(text)
            # Restore translations safety net
            final_list = self._restore_translations(filtered_list, violations)
            return final_list, text
            
        safe_log(f"Smart Filter failed: {error}", "ERROR")
        return violations, f"FAILED: {error}"

    def _normalize_key(self, text: str) -> str:
        if not text: return ""
        return re.sub(r'[\W_]+', '', text.lower())[:100]

    def _restore_translations(self, unique_list: List[Violation], original_list: List[Violation]) -> List[Violation]:
        text_map = {} 
        backup_map = {}
        for v in original_list:
            if v.translation:
                norm_text = self._normalize_key(v.problematic_text)
                if norm_text: text_map[norm_text] = (v.translation, v.rewrite_translation)
                backup_key = f"{v.page_number}-{v.violation_type}"
                backup_map[backup_key] = (v.translation, v.rewrite_translation)
        for v in unique_list:
            if v.translation: continue
            norm_text = self._normalize_key(v.problematic_text)
            if norm_text in text_map:
                v.translation, v.rewrite_translation = text_map[norm_text]
                continue 
            backup_key = f"{v.page_number}-{v.violation_type}"
            if backup_key in backup_map:
                 v.translation, v.rewrite_translation = backup_map[backup_key]
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
            if v.translation: md.append(f"> 🌐 **Translation:** _{v.translation}_")
            md.append(f"**Explanation:** {v.explanation}")
            md.append(f"**Guideline:** Section {v.guideline_section} (Page {v.page_number})")
            md.append(f"**Suggested Fix:** \"{v.suggested_rewrite}\"")
            if v.rewrite_translation: md.append(f"> 🛠️ **Fix Translation:** _{v.rewrite_translation}_")
            md.append("\n---\n")
            count += 1
        return "\n".join(md)

async def analyze_content(content: str, casino_mode: bool, debug_mode: bool, audit_count: int = 5) -> Dict[str, Any]:
    orchestrator = AuditOrchestrator()
    return await orchestrator.run_analysis(content, casino_mode, debug_mode, audit_count)
