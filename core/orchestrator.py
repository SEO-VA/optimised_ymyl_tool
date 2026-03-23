#!/usr/bin/env python3
"""
Audit Orchestrator - 3-Stage Pipeline (Detect → Verify → Finalize)
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

DETECTION_MODEL = "gpt-5.4-nano"
VERIFICATION_MODEL = "gpt-5.4-mini"
FINALIZATION_MODEL = "gpt-5.4-nano"


class AuditOrchestrator:
    def __init__(self, service=None, settings: Optional[Dict[str, Any]] = None):
        self.service = service or openai_service
        self.settings = settings or {
            'lens_financial_instructions': st.secrets.get("lens_financial_instructions"),
            'lens_safety_instructions': st.secrets.get("lens_safety_instructions"),
            'lens_trust_instructions': st.secrets.get("lens_trust_instructions"),
            'verifier_instructions': st.secrets.get("verifier_instructions"),
            'finalizer_instructions': st.secrets.get("finalizer_instructions"),
            'ymyl_knowledge_vector_store_id': st.secrets.get("ymyl_knowledge_vector_store_id"),
            'casino_vector_store_id': st.secrets.get("casino_vector_store_id"),
        }

    async def run_analysis(self, content_json: str, topic_description: str, debug_mode: bool) -> Dict[str, Any]:
        start_time = time.time()
        config_error = self._validate_configuration()
        if config_error:
            safe_log(f"Orchestrator: {config_error}", "ERROR")
            return {"success": False, "error": config_error}

        payload_json, global_context = self._build_analyzer_payload(content_json, topic_description)
        knowledge_vs_ids = [self.settings['ymyl_knowledge_vector_store_id']]
        full_pdf_vs_ids = [self.settings['casino_vector_store_id']]

        # ── STAGE 1: Detection (3 lenses in parallel) ────────────────────────
        lens_configs = [
            ("financial_accuracy", self.settings['lens_financial_instructions']),
            ("safety_responsibility", self.settings['lens_safety_instructions']),
            ("trust_quality", self.settings['lens_trust_instructions']),
        ]

        safe_log("Orchestrator: Stage 1 — Running 3 detection lenses in parallel...")
        detection_tasks = [
            self.service.get_response(
                content=payload_json,
                instructions=self._inject_topic(instructions, topic_description),
                task_name=f"Lens:{name}",
                vector_store_ids=knowledge_vs_ids,
                force_tool=True,
                model_override=DETECTION_MODEL,
            )
            for name, instructions in lens_configs
        ]
        detection_results = await asyncio.gather(*detection_tasks)

        all_candidates: List[Violation] = []
        raw_debug_detection = []
        successful_lenses = 0

        for (lens_name, _), result in zip(lens_configs, detection_results):
            violations, parse_success, parse_source = self._extract_violations(result)
            if result.success and parse_success and isinstance(violations, list):
                successful_lenses += 1
                for v in violations:
                    v.source_lens = lens_name
                all_candidates.extend(violations)
            else:
                safe_log(f"Lens:{lens_name} failed: {result.error_message or 'parse error'}", "WARNING")
            if debug_mode:
                raw_debug_detection.append(
                    self._build_debug_entry(lens_name, result, violations if isinstance(violations, list) else [], parse_success, parse_source)
                )

        if successful_lenses == 0:
            debug_package = {"detection": raw_debug_detection} if debug_mode else None
            return {"success": False, "error": "All detection lenses failed.", "debug_info": debug_package}

        safe_log(f"Orchestrator: Stage 1 complete — {len(all_candidates)} candidates from {successful_lenses} lenses.")

        # ── STAGE 2: Verification (single batch call) ─────────────────────────
        verified_violations: List[Violation] = []
        verifier_debug: Dict[str, Any] = {"status": "skipped"}

        if all_candidates:
            safe_log(f"Orchestrator: Stage 2 — Verifying {len(all_candidates)} candidates...")
            verifier_payload = json.dumps({
                "global_context": global_context,
                "original_content": content_json,
                "candidates": [v.to_dict() for v in all_candidates],
            }, indent=2)

            verifier_result = await self.service.get_response(
                content=verifier_payload,
                instructions=self.settings['verifier_instructions'],
                task_name="Verifier",
                vector_store_ids=full_pdf_vs_ids,
                force_tool=True,
                model_override=VERIFICATION_MODEL,
                timeout_seconds=400,
            )

            parsed, verify_ok, verify_source = self._extract_violations(verifier_result)
            if verifier_result.success and verify_ok and isinstance(parsed, list):
                verified_violations = parsed
            else:
                safe_log("Verifier failed — falling back to raw candidates.", "WARNING")
                verified_violations = all_candidates

            verifier_debug = self._build_debug_entry(
                "verifier", verifier_result,
                verified_violations, verify_ok, verify_source
            )
            safe_log(f"Orchestrator: Stage 2 complete — {len(verified_violations)} violations survived verification.")

        # ── STAGE 3: Finalization ─────────────────────────────────────────────
        final_violations: List[Violation] = []
        finalizer_debug: Dict[str, Any] = {"status": "skipped"}

        if verified_violations:
            safe_log(f"Orchestrator: Stage 3 — Finalizing {len(verified_violations)} violations...")
            finalizer_payload = json.dumps({
                "context": global_context,
                "violations_input": [v.to_dict() for v in verified_violations],
            }, indent=2)

            finalizer_result = await self.service.get_response(
                content=finalizer_payload,
                instructions=self.settings['finalizer_instructions'],
                task_name="Finalizer",
                vector_store_ids=None,
                force_tool=False,
                model_override=FINALIZATION_MODEL,
                timeout_seconds=300,
            )

            parsed, final_ok, final_source = self._extract_violations(finalizer_result)
            if finalizer_result.success and final_ok and isinstance(parsed, list):
                final_violations = parsed
            else:
                safe_log("Finalizer failed — falling back to verified violations.", "WARNING")
                final_violations = verified_violations

            finalizer_debug = self._build_debug_entry(
                "finalizer", finalizer_result,
                final_violations, final_ok, final_source
            )
            safe_log(f"Orchestrator: Stage 3 complete — {len(final_violations)} unique violations.")

        report_md = self._generate_markdown(final_violations, successful_lenses)

        debug_package = None
        if debug_mode:
            debug_package = {
                "detection": raw_debug_detection,
                "verification": verifier_debug,
                "finalization": finalizer_debug,
            }

        return {
            "success": True,
            "report": report_md,
            "violations": final_violations,
            "processing_time": time.time() - start_time,
            "total_violations_found": len(all_candidates),
            "unique_violations": len(final_violations),
            "debug_info": debug_package,
            "word_bytes": None,
        }

    def _inject_topic(self, instructions: str, topic_description: str) -> str:
        return instructions.replace("{topic_description}", topic_description or "online casino affiliate site")

    def _build_analyzer_payload(self, content_json: str, topic_description: str) -> Tuple[str, Dict]:
        h1_text = "Unknown Title"
        try:
            data = json.loads(content_json)
            for section in data.get("sections", [])[:3]:
                content = section.get("content", "")
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("# ") and not line.startswith("## "):
                        h1_text = line[2:].strip()
                        break
                if h1_text != "Unknown Title":
                    break
        except Exception:
            pass

        global_context = {
            "primary_topic": h1_text,
            "content_type": topic_description or "Commercial Review",
            "ymyl_category": "Financial/Gambling",
            "global_assumptions": {
                "affiliate_disclosure": "Compliant",
                "site_reputation": "Neutral/Good",
            },
        }
        payload = {"global_context": global_context, "chunk_text": content_json}
        return json.dumps(payload, indent=2), global_context

    def _extract_violations(self, result: OpenAIResponseResult) -> Tuple[List[Violation], bool, str]:
        if result.parsed_payload is not None:
            violations, parse_success = ResponseParser.parse_payload_to_violations(result.parsed_payload)
            return violations, parse_success, "structured"
        if result.output_text:
            violations, parse_success = ResponseParser.parse_text_to_violations(result.output_text)
            return violations, parse_success, "legacy_text"
        return [], False, "none"

    def _build_debug_entry(self,
                           stage_name: str,
                           result: OpenAIResponseResult,
                           violations: List[Violation],
                           parse_success: bool,
                           parse_source: str) -> Dict[str, Any]:
        return {
            "stage": stage_name,
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

    def _validate_configuration(self) -> Optional[str]:
        required = {
            "lens_financial_instructions": self.settings.get("lens_financial_instructions"),
            "lens_safety_instructions": self.settings.get("lens_safety_instructions"),
            "lens_trust_instructions": self.settings.get("lens_trust_instructions"),
            "verifier_instructions": self.settings.get("verifier_instructions"),
            "finalizer_instructions": self.settings.get("finalizer_instructions"),
            "ymyl_knowledge_vector_store_id": self.settings.get("ymyl_knowledge_vector_store_id"),
            "casino_vector_store_id": self.settings.get("casino_vector_store_id"),
        }
        missing = [k for k, v in required.items() if not v]
        service_error = self.service.validate_runtime_configuration(
            vector_store_ids=[self.settings.get("ymyl_knowledge_vector_store_id")]
        )
        if service_error:
            missing.append(service_error)
        if missing:
            return "Configuration error: " + ", ".join(str(m) for m in missing)
        return None

    def _generate_markdown(self, violations: List[Violation], lens_count: int) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        md = [f"# YMYL Compliance Report\n**Date:** {date_str}\n**Detection Lenses:** {lens_count}\n---"]
        if not violations:
            md.append("\n✅ **No violations found.")
            return "\n".join(md)

        count = 1
        for v in violations:
            if "no violation" in v.violation_type.lower():
                continue
            emoji = "🔴" if v.severity.value == "critical" else "🟠" if v.severity.value in ["high", "medium"] else "🔵"

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


async def analyze_content(content: str, topic_description: str, debug_mode: bool) -> Dict[str, Any]:
    orchestrator = AuditOrchestrator()
    return await orchestrator.run_analysis(content, topic_description, debug_mode)
