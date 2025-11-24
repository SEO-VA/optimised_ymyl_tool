#!/usr/bin/env python3
"""
Audit Orchestrator Module - Clean & Simple
Flow:
1. Send content + backpack to Auditor Assistants (Parallel).
2. Send raw violations + backpack to Deduplicator Assistant.
3. Generate Report.
"""

import asyncio
import json
import time
import re
import streamlit as st
from typing import List, Dict, Any, Tuple
from datetime import datetime

from core.models import Violation
from core.service import openai_service
from core.parser import ResponseParser
from utils.helpers import safe_log

# Safety limit
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

    async def run_analysis(self, content_json: str, casino_mode: bool, debug_mode: bool, audit_count: int = 5) -> Dict[str, Any]:
        start_time = time.time()
        
        # 1. Select Assistant
        target_assistant_id = self.settings['casino_assistant_id'] if casino_mode else self.settings['regular_assistant_id']
        
        safe_log(f"Orchestrator: Starting {audit_count} audits...")

        # 2. Run Parallel Audits
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)

        async def _run_audit(index):
            async with semaphore:
                await asyncio.sleep(index * 0.5) 
                return await openai_service.get_response_async(
                    content=content_json,
                    assistant_id=target_assistant_id,
                    task_name=f"Audit #{index+1}",
                    json_mode=True
                )

        tasks = [_run_audit(i) for i in range(audit_count)]
        raw_results = await asyncio.gather(*tasks)
        
        all_violations = []
        successful_audits = 0
        raw_debug_data = []

        for i, (success, text, error) in enumerate(raw_results):
            audit_id = i + 1
            if success and text:
                violations = ResponseParser.parse_to_violations(text)
                # Accept empty list as valid success
                if isinstance(violations, list):
                    successful_audits += 1
                    for v in violations:
                        v.source_audit_id = i + 1
                    all_violations.extend(violations)
                
                if debug_mode:
                    raw_debug_data.append({
                        "audit_number": audit_id,
                        "raw_response": text,
                        "parsed_count": len(violations) if violations else 0
                    })
            else:
                safe_log(f"Audit #{audit_id} failed: {error}", "WARNING")

        if successful_audits == 0:
            return {"success": False, "error": "All audits failed."}

        # 3. Deduplication (Merge)
        dedup_raw_text = "Skipped"
        final_violations = []
        
        # Always deduplicate if we have results
        if all_violations:
            # Extract Backpack (Chunk 0) to give Deduplicator context
            backpack_context = "Global Context Not Found"
            try:
                data = json.loads(content_json)
                if data.get("big_chunks") and data["big_chunks"][0]["big_chunk_index"] == 0:
                    backpack_context = json.dumps(data["big_chunks"][0])
            except: pass

            final_violations, dedup_raw_text = await self._run_deduplication(
                all_violations, 
                backpack_context
            )
        else:
            final_violations = []
            dedup_raw_text = "Skipped (No violations found)"

        # 4. Report
        report_md = self._generate_markdown(final_violations, successful_audits)
        
        debug_package = None
        if debug_mode:
            debug_package = {
                "audits": raw_debug_data,
                "deduplicator_raw": dedup_raw_text,
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

    async def _run_deduplication(self, violations: List[Violation], context_backpack: str) -> Tuple[List[Violation], str]:
        """
        Simple Merge: Sends violations to the Assistant to remove duplicates.
        """
        if not violations: return [], "No violations"

        # Simple Payload: Data + Context
        payload = {
            "task": "merge_duplicates",
            "context_backpack": context_backpack, 
            "violations_input": [v.to_dict() for v in violations]
        }
        
        payload_json = json.dumps(payload, indent=2)
        
        success, text, error = await openai_service.get_response_async(
            content=payload_json,
            assistant_id=self.settings['deduplicator_assistant_id'],
            task_name="Deduplicator",
            timeout_seconds=400,
            json_mode=True
        )
        
        if success and text:
            deduped_list = ResponseParser.parse_to_violations(text)
            # Safety Net: Restore translations if AI dropped them
            final_list = self._restore_translations(deduped_list, violations)
            return final_list, text
        
        safe_log(f"Deduplication failed: {error}", "ERROR")
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
            else:
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
            if "no violation" in v.violation_type.lower(): continue

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
        return "\n".join(md)

async def analyze_content(content: str, casino_mode: bool, debug_mode: bool, audit_count: int = 5) -> Dict[str, Any]:
    orchestrator = AuditOrchestrator()
    return await orchestrator.run_analysis(content, casino_mode, debug_mode, audit_count)
