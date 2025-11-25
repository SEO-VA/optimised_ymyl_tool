#!/usr/bin/env python3
"""
Audit Orchestrator - Standard Edition
"""

import asyncio
import json
import time
import streamlit as st
from typing import List, Dict, Any, Tuple
from datetime import datetime
from core.models import Violation
from core.service import openai_service
from core.parser import ResponseParser
from utils.helpers import safe_log

MAX_CONCURRENT_AUDITS = 5

class AuditOrchestrator:
    def __init__(self):
        self.settings = {
            'regular_assistant_id': st.secrets["regular_assistant_id"],
            'casino_assistant_id': st.secrets["casino_assistant_id"],
            'deduplicator_assistant_id': st.secrets["deduplicator_assistant_id"]
        }

    async def run_analysis(self, content_json: str, casino_mode: bool, debug_mode: bool, audit_count: int = 5) -> Dict[str, Any]:
        start_time = time.time()
        target_assistant_id = self.settings['casino_assistant_id'] if casino_mode else self.settings['regular_assistant_id']
        analyzer_payload_json, global_context_dict = self._build_analyzer_payload(content_json)
        
        safe_log(f"Orchestrator: Starting {audit_count} audits...")
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)

        async def _run_audit(index):
            async with semaphore:
                await asyncio.sleep(index * 1.0) 
                return await openai_service.get_assistant_response(
                    content=analyzer_payload_json,
                    assistant_id=target_assistant_id,
                    task_name=f"Audit #{index+1}"
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
                if isinstance(violations, list):
                    successful_audits += 1
                    for v in violations: v.source_audit_id = i + 1
                    all_violations.extend(violations)
                if debug_mode:
                    raw_debug_data.append({"audit_number": audit_id, "raw_response": text, "parsed_count": len(violations) if violations else 0})
            else:
                safe_log(f"Audit #{audit_id} failed: {error}", "WARNING")

        if successful_audits == 0: return {"success": False, "error": "All audits failed."}

        # Deduplication (Always runs)
        final_violations = []
        dedup_raw_text = "Skipped"
        if all_violations:
            final_violations, dedup_raw_text = await self._run_deduplication(all_violations, global_context_dict)
        
        report_md = self._generate_markdown(final_violations, successful_audits)
        
        debug_package = None
        if debug_mode:
            debug_package = {"audits": raw_debug_data, "deduplicator_raw": dedup_raw_text}

        return {
            "success": True, "report": report_md, "violations": final_violations,
            "processing_time": time.time() - start_time, "total_violations_found": len(all_violations),
            "unique_violations": len(final_violations), "debug_info": debug_package, "word_bytes": None
        }

    def _build_analyzer_payload(self, content_json: str) -> Tuple[str, Dict]:
        h1_text = "Unknown Title"
        try:
            data = json.loads(content_json)
            for chunk in data.get("big_chunks", [])[:3]:
                for item in chunk.get("small_chunks", []):
                    if item.startswith("H1:"): h1_text = item.replace("H1:", "").strip(); break
                if h1_text != "Unknown Title": break
        except: pass

        global_context = {
            "primary_topic": h1_text,
            "content_type": "Commercial Review", 
            "ymyl_category": "Financial/Gambling",
            "global_assumptions": {"site_identity": "Compliant", "affiliate_disclosure": "Compliant", "site_reputation": "Neutral/Good"}
        }
        payload = {"global_context": global_context, "chunk_text": content_json}
        return json.dumps(payload, indent=2), global_context

    async def _run_deduplication(self, violations: List[Violation], context_backpack: Dict) -> Tuple[List[Violation], str]:
        payload = {"context_backpack": context_backpack, "violations_input": [v.to_dict() for v in violations]}
        success, text, error = await openai_service.get_assistant_response(
            content=json.dumps(payload, indent=2),
            assistant_id=self.settings['deduplicator_assistant_id'],
            task_name="Deduplicator",
            timeout_seconds=400
        )
        if success and text:
            return ResponseParser.parse_to_violations(text), text
        return violations, f"FAILED: {error}"

    def _generate_markdown(self, violations: List[Violation], audit_count: int) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        md = [f"# YMYL Compliance Report\n**Date:** {date_str}\n**Audits Performed:** {audit_count}\n---"]
        if not violations:
            md.append("\n✅ **No violations found.**"); return "\n".join(md)
            
        count = 1
        for v in violations:
            if "no violation" in v.violation_type.lower(): continue
            emoji = "🔴" if v.severity.value == "critical" else "🟠" if v.severity.value in ["high", "medium"] else "🔵"
            
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

# THIS FUNCTION MUST BE AT THE BOTTOM OF THE FILE
async def analyze_content(content: str, casino_mode: bool, debug_mode: bool, audit_count: int = 5) -> Dict[str, Any]:
    orchestrator = AuditOrchestrator()
    return await orchestrator.run_analysis(content, casino_mode, debug_mode, audit_count)
