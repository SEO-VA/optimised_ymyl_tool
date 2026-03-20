#!/usr/bin/env python3
"""
Audit Orchestrator - Dashboard Prompt Edition
"""

import asyncio
import json
import time
import streamlit as st
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from core.models import Violation, OpenAIResponseResult
from core.service import openai_service
from core.parser import ResponseParser
from utils.helpers import safe_log

MAX_CONCURRENT_AUDITS = 5

class AuditOrchestrator:
    def __init__(self, service=None, settings: Optional[Dict[str, Any]] = None):
        self.service = service or openai_service
        self.settings = settings or {
            'regular_instructions': st.secrets.get("regular_instructions"),
            'casino_instructions': st.secrets.get("casino_instructions"),
            'deduplicator_instructions': st.secrets.get("deduplicator_instructions"),
            'regular_vector_store_id': st.secrets.get("regular_vector_store_id"),
            'casino_vector_store_id': st.secrets.get("casino_vector_store_id"),
        }

    async def run_analysis(self, content_json: str, casino_mode: bool, debug_mode: bool, audit_count: int = 5) -> Dict[str, Any]:
        start_time = time.time()
        config_error = self._validate_configuration(casino_mode)
        if config_error:
            safe_log(f"Orchestrator: {config_error}", "ERROR")
            return {"success": False, "error": config_error}

        analyzer_payload_json, global_context_dict = self._build_analyzer_payload(content_json)
        
        if casino_mode:
            target_instructions = self.settings['casino_instructions']
            target_vs_ids = [self.settings['casino_vector_store_id']]
        else:
            target_instructions = self.settings['regular_instructions']
            target_vs_ids = [self.settings['regular_vector_store_id']]

        safe_log(f"Orchestrator: Starting {audit_count} audits...")
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)

        async def _run_audit(index):
            async with semaphore:
                await asyncio.sleep(index * 1.0)
                return await self.service.get_response(
                    content=analyzer_payload_json,
                    instructions=target_instructions,
                    task_name=f"Audit #{index+1}",
                    vector_store_ids=target_vs_ids,
                    force_tool=True,  # CRITICAL: Forces Analyzer to search PDF
                )

        tasks = [_run_audit(i) for i in range(audit_count)]
        raw_results = await asyncio.gather(*tasks)
        
        all_violations = []
        successful_audits = 0
        raw_debug_data = []

        for i, result in enumerate(raw_results):
            audit_id = i + 1
            violations, parse_success, parse_source = self._extract_violations(result)
            if result.success and parse_success:
                if isinstance(violations, list):
                    successful_audits += 1
                    for v in violations: v.source_audit_id = i + 1
                    all_violations.extend(violations)
                if debug_mode:
                    raw_debug_data.append(self._build_debug_entry(audit_id, result, violations, parse_success, parse_source))
            else:
                safe_log(f"Audit #{audit_id} failed: {result.error_message or 'Unknown failure'}", "WARNING")
                if debug_mode:
                    raw_debug_data.append(self._build_debug_entry(audit_id, result, violations, parse_success, parse_source))

        if successful_audits == 0:
            debug_package = {"audits": raw_debug_data} if debug_mode else None
            return {"success": False, "error": "All audits failed.", "debug_info": debug_package}

        # Deduplication (Always runs)
        final_violations = []
        dedup_result = {"status": "skipped", "raw_response": "Skipped"}
        if all_violations:
            final_violations, dedup_result = await self._run_deduplication(all_violations, global_context_dict)
        
        report_md = self._generate_markdown(final_violations, successful_audits)
        
        debug_package = None
        if debug_mode:
            debug_package = {"audits": raw_debug_data, "deduplicator": dedup_result}

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

    async def _run_deduplication(self, violations: List[Violation], context_backpack: Dict) -> Tuple[List[Violation], Dict[str, Any]]:
        payload = {"context_backpack": context_backpack, "violations_input": [v.to_dict() for v in violations]}
        
        # DO NOT force tool here. Deduplicator is logic-only.
        result = await self.service.get_response(
            content=json.dumps(payload, indent=2),
            instructions=self.settings['deduplicator_instructions'],
            task_name="Deduplicator",
            timeout_seconds=400,
            vector_store_ids=None,
            force_tool=False,
        )
        parsed_violations, parse_success, parse_source = self._extract_violations(result)
        debug_payload = self._build_debug_entry(0, result, parsed_violations, parse_success, parse_source)
        debug_payload["task"] = "deduplicator"

        if result.success and parse_success:
            return parsed_violations, debug_payload
        debug_payload["fallback_applied"] = True
        return violations, debug_payload

    def _extract_violations(self, result: OpenAIResponseResult) -> Tuple[List[Violation], bool, str]:
        if result.parsed_payload is not None:
            violations, parse_success = ResponseParser.parse_payload_to_violations(result.parsed_payload)
            return violations, parse_success, "structured"
        if result.output_text:
            violations, parse_success = ResponseParser.parse_text_to_violations(result.output_text)
            return violations, parse_success, "legacy_text"
        return [], False, "none"

    def _build_debug_entry(self,
                           audit_id: int,
                           result: OpenAIResponseResult,
                           violations: List[Violation],
                           parse_success: bool,
                           parse_source: str) -> Dict[str, Any]:
        return {
            "audit_number": audit_id,
            "transport_success": result.success,
            "status": result.status,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "parse_success": parse_success,
            "parse_source": parse_source,
            "parsed_count": len(violations),
            "parsed_payload": result.parsed_payload,
            "raw_response": result.output_text,
            "tool_summary": result.tool_summary,
            "request_meta": result.request_meta,
            "raw_output_items": result.raw_output_items,
        }

    def _validate_configuration(self, casino_mode: bool) -> Optional[str]:
        required_settings = {
            "regular_instructions": self.settings.get("regular_instructions"),
            "casino_instructions": self.settings.get("casino_instructions"),
            "deduplicator_instructions": self.settings.get("deduplicator_instructions"),
        }
        target_key = "casino_vector_store_id" if casino_mode else "regular_vector_store_id"
        required_settings[target_key] = self.settings.get(target_key)

        missing = [key for key, value in required_settings.items() if not value]
        service_error = self.service.validate_runtime_configuration(
            vector_store_ids=[self.settings.get(target_key)] if target_key in required_settings else None
        )
        if service_error:
            missing.append(service_error)

        if missing:
            return "Configuration error: " + ", ".join(str(item) for item in missing)
        return None

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

async def analyze_content(content: str, casino_mode: bool, debug_mode: bool, audit_count: int = 5) -> Dict[str, Any]:
    orchestrator = AuditOrchestrator()
    return await orchestrator.run_analysis(content, casino_mode, debug_mode, audit_count)
