#!/usr/bin/env python3

import unittest
from unittest.mock import patch

from core.models import OpenAIResponseResult
from core.orchestrator import AuditOrchestrator


def structured_result(problematic_text="Risk-free winnings", success=True):
    return OpenAIResponseResult(
        success=success,
        status="completed" if success else "failed",
        output_text='{"violations": [{"problematic_text": "%s", "violation_type": "Misleading claim", "explanation": "Guarantee language is not allowed.", "guideline_section": "4.2", "page_number": 3, "severity": "critical", "suggested_rewrite": "Avoid guarantee language."}]}' % problematic_text if success else None,
        parsed_payload={
            "violations": [{
                "problematic_text": problematic_text,
                "violation_type": "Misleading claim",
                "explanation": "Guarantee language is not allowed.",
                "guideline_section": "4.2",
                "page_number": 3,
                "severity": "critical",
                "suggested_rewrite": "Avoid guarantee language.",
            }]
        } if success else None,
        tool_summary={"file_search_used": True, "file_search_calls": 1, "file_search_result_count": 1, "file_search_statuses": ["completed"], "file_search_queries": ["ymyl"], "requested_tools": ["file_search"], "tool_choice": "forced_file_search"},
        request_meta={"task_name": "Audit"},
        error_type=None if success else "api_error",
        error_message=None if success else "Call failed",
    )


class FakeService:
    def __init__(self, responses, config_error=None):
        self.responses = list(responses)
        self.calls = []
        self.config_error = config_error

    def validate_runtime_configuration(self, vector_store_ids=None):
        return self.config_error

    async def get_response(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class AuditOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = {
            "regular_instructions": "Return JSON",
            "casino_instructions": "Return JSON",
            "deduplicator_instructions": "Return JSON",
            "regular_vector_store_id": "vs_regular",
            "casino_vector_store_id": "vs_casino",
        }
        self.content_json = '{"big_chunks":[{"small_chunks":["H1: Sample Heading"]}]}'

    async def test_all_audits_fail(self):
        service = FakeService([
            OpenAIResponseResult(success=False, status="failed", error_type="api_error", error_message="boom"),
            OpenAIResponseResult(success=False, status="failed", error_type="api_error", error_message="boom"),
        ])
        orchestrator = AuditOrchestrator(service=service, settings=self.settings)

        async def no_sleep(_):
            return None

        with patch("core.orchestrator.asyncio.sleep", new=no_sleep):
            result = await orchestrator.run_analysis(self.content_json, casino_mode=False, debug_mode=True, audit_count=2)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "All audits failed.")
        self.assertEqual(len(result["debug_info"]["audits"]), 2)

    async def test_partial_success_and_debug_capture(self):
        service = FakeService([
            structured_result("Risk-free winnings"),
            OpenAIResponseResult(success=False, status="failed", error_type="api_error", error_message="boom"),
            OpenAIResponseResult(
                success=True,
                status="completed",
                output_text='{"violations": []}',
                parsed_payload={"violations": []},
                tool_summary={"requested_tools": [], "tool_choice": "auto", "file_search_used": False, "file_search_calls": 0, "file_search_statuses": [], "file_search_queries": [], "file_search_result_count": 0},
                request_meta={"task_name": "Deduplicator"},
            ),
        ])
        orchestrator = AuditOrchestrator(service=service, settings=self.settings)

        async def no_sleep(_):
            return None

        with patch("core.orchestrator.asyncio.sleep", new=no_sleep):
            result = await orchestrator.run_analysis(self.content_json, casino_mode=False, debug_mode=True, audit_count=2)

        self.assertTrue(result["success"])
        self.assertEqual(result["total_violations_found"], 1)
        self.assertEqual(len(result["debug_info"]["audits"]), 2)
        self.assertIn("deduplicator", result["debug_info"])
        self.assertTrue(result["debug_info"]["audits"][0]["tool_summary"]["file_search_used"])

    async def test_deduplicator_failure_falls_back_to_original_violations(self):
        service = FakeService([
            structured_result("Risk-free winnings"),
            OpenAIResponseResult(success=False, status="failed", error_type="api_error", error_message="dedup failed"),
        ])
        orchestrator = AuditOrchestrator(service=service, settings=self.settings)

        async def no_sleep(_):
            return None

        with patch("core.orchestrator.asyncio.sleep", new=no_sleep):
            result = await orchestrator.run_analysis(self.content_json, casino_mode=False, debug_mode=True, audit_count=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["unique_violations"], 1)
        self.assertEqual(result["violations"][0].problematic_text, "Risk-free winnings")
        self.assertTrue(result["debug_info"]["deduplicator"]["fallback_applied"])


if __name__ == "__main__":
    unittest.main()
