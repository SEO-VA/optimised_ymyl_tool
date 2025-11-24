#!/usr/bin/env python3
"""
Audit Orchestrator Module
The Strategy Layer. Coordinates the Multi-Audit Workflow.
Key Features:
1. Global Context Injection (The "Backpack" - Fixes False Positives).
2. Rate Limit Protection (Semaphore).
3. Double Sanitation (Removes 'No Violation' noise).
4. Translation Restoration (Prevents data loss).
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

# CONTROL CONCURRENCY (3 is safe for most tiers)
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
        
        # --- STEP 0: CONTEXT BACKPACK (Crucial for Accuracy) ---
        # We inject the Intro/Summary/Warnings into EVERY chunk so the AI knows the rules.
        enriched_json = self._inject_global_context(content_json)
        
        target_assistant_id = self.casino_id if casino_mode else self.regular_id
        safe_log(f"Orchestrator: Starting {audit_count} audits...")

        # --- STEP 1: PARALLEL AUDITS ---
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)

        async def _run_with_semaphore(index):
            async with semaphore:
                await asyncio.sleep(index * 0.5) # Stagger to avoid rate limits
                return await openai_service.get_response_async(
                    content=enriched_json, # Send the enriched version!
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
                    all_violations.extend(violations)
                
                if debug_mode:
                    raw_debug_data.append({
                        "audit_number": audit_id,
                        "raw_response": text,
                        "parsed_count": len(violations)
                    })
            else:
                safe_log(f"Audit #{audit_id} failed: {error}", "WARNING")

        if successful_audits == 0:
            return {"success": False, "error": "All audits failed."}

        # --- SANITATION 1: CLEAN INPUTS ---
        # Filter out "No violation" objects BEFORE deduplication
        clean_input_violations = self._sanitize_violations(all_violations)

        # --- STEP 2: DEDUPLICATION ---
        dedup_raw_text = None
        unique_violations = []
        
        if audit_count > 1 and clean_input_violations:
            unique_violations, dedup_raw_text = await self._run_deduplication(clean_input_violations)
        else:
            unique_violations = clean_input_violations
            dedup_raw_text = "Skipped (Test Mode or No Violations)"
        
        # --- SANITATION 2: CLEAN OUTPUTS ---
        # Filter again in case Deduplicator added noise
        final_violations = self._sanitize_violations(unique_violations)
        
        # --- STEP 3: REPORTING ---
        report_md = self._generate_markdown(final_violations, successful_audits)
        
        debug_package = None
        if debug_mode:
            debug_package = {
                "audits": raw_debug_data,
                "deduplicator_raw": dedup_raw_text,
                "input_violation_count": len(all_violations),
                "output_violation_count": len(final_violations)
            }

        return {
            "success": True,
            "report": report_md,
            "violations": final_violations,
            "processing_time": time.time() - start_time,
            "total_violations_found": len(clean_input_violations),
            "unique_violations": len(final_violations),
            "debug_info": debug_package,
            "debug_mode": debug_mode,
            "word_bytes": None
        }

    def _inject_global_context(self, json_content: str) -> str:
        """
        Harvests H1, Lead, Summary, and Warnings from the whole document
        and injects them into EVERY chunk.
        """
        try:
            data = json.loads(json_content)
            chunks = data.get('big_chunks', [])
            
            # 1. Harvest Context
            context_items = []
            for chunk in chunks:
                for item in chunk.get('small_chunks', []):
                    # Capture Metadata
                    if any(prefix in item for prefix in ['H1:', 'LEAD:', 'SUMMARY:', 'SUBTITLE:']):
                        context_items.append(item)
                    # Capture Warnings (Crucial for False Positive prevention)
                    if 'WARNING' in item or '18+' in item:
                        context_items.append(item)
            
            context_items = list(set(context_items)) # Remove dupes
            if not context_items: return json_content
                
            context_str = " || ".join(context_items)
            
            # 2. Inject into Chunks
            for chunk in chunks:
                # Add context as the FIRST item so AI reads it before the content
                chunk['small_chunks'].insert(0, f"*** GLOBAL PAGE CONTEXT (Apply to this section): {context_str} ***")
                
            return json.dumps(data, indent=2, ensure_ascii=False)
        except Exception as e:
            safe_log(f"Context Injection Failed: {e}", "ERROR")
            return json_content

    def _sanitize_violations(self, violations: List[Violation]) -> List[Violation]:
        """Removes 'No violation found' objects."""
        cleaned = []
        blacklist = ["no violation", "no issue", "compliant", "none", "n/a", "safe", "passed"]

        for v in violations:
            v_type = v.violation_type.lower().strip() if v.violation_type else ""
            if not v_type or any(term in v_type for term in blacklist):
                continue
            if not v.problematic_text or v.problematic_text.lower() in ["n/a", "none", ""]:
                continue
            cleaned.append(v)
        return cleaned

    async def _run_deduplication(self, all_violations: List[Violation]) -> Tuple[List[Violation], str]:
        if not all_violations: return [], "No violations"

        payload = {
            "task": "deduplicate_violations_and_merge",
            "IMPORTANT_RULE": "You MUST PRESERVE the 'translation' and 'rewrite_translation' fields. Do NOT create 'no violation' objects.",
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
            # Restore translations (Safety Net)
            final_list = self._restore_translations(deduped_list, all_violations)
            return final_list, text
        
        safe_log(f"Deduplication failed: {error}", "ERROR")
        return all_violations, f"FAILED: {error}"

    def _normalize_key(self, text: str) -> str:
        if not text: return ""
        return re.sub(r'[\W_]+', '', text.lower())[:100]

    def _restore_translations(self, unique_list: List[Violation], original_list: List[Violation]) -> List[Violation]:
        """Fuzzy match to restore translations lost during deduplication"""
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
