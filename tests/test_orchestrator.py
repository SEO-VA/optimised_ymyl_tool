#!/usr/bin/env python3

import json
import unittest

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
        request_meta={"task_name": "Lens"},
        error_type=None if success else "api_error",
        error_message=None if success else "Call failed",
    )


def empty_result():
    return OpenAIResponseResult(
        success=True,
        status="completed",
        output_text='{"violations": []}',
        parsed_payload={"violations": []},
        tool_summary={"requested_tools": [], "tool_choice": "auto", "file_search_used": False, "file_search_calls": 0, "file_search_statuses": [], "file_search_queries": [], "file_search_result_count": 0},
        request_meta={"task_name": "Stage"},
    )


SAMPLE_CONTENT_JSON = json.dumps({
    "sections": [
        {"index": 1, "name": "Page Metadata", "content": "# Sample Casino Review\n\n**Published:** 2024-01-15"},
        {"index": 2, "name": "Bonuses", "content": "## Bonuses\n\nGet 100% up to $500 on first deposit."},
    ]
})

MINIMAL_SETTINGS = {
    "lens_financial_instructions": "Analyze financial claims.",
    "lens_safety_instructions": "Analyze safety claims.",
    "lens_trust_instructions": "Analyze trust signals.",
    "verifier_instructions": "Verify violations.",
    "finalizer_instructions": "Finalize violations.",
    "ymyl_knowledge_vector_store_id": "vs_ymyl",
    "casino_vector_store_id": "vs_casino",
}


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

    async def test_all_lenses_fail_returns_error(self):
        failed = OpenAIResponseResult(success=False, status="failed", error_type="api_error", error_message="boom")
        service = FakeService([failed, failed, failed])
        orchestrator = AuditOrchestrator(service=service, settings=MINIMAL_SETTINGS)

        result = await orchestrator.run_analysis(SAMPLE_CONTENT_JSON, "casino review", debug_mode=False)

        self.assertFalse(result["success"])
        self.assertIn("All detection lenses failed", result["error"])

    async def test_successful_3stage_pipeline(self):
        # 3 detection lenses + 1 verifier + 1 finalizer
        service = FakeService([
            structured_result("Risk-free winnings"),
            structured_result("Guaranteed profits"),
            empty_result(),   # third lens finds nothing
            structured_result("Risk-free winnings"),  # verifier
            structured_result("Risk-free winnings"),  # finalizer
        ])
        orchestrator = AuditOrchestrator(service=service, settings=MINIMAL_SETTINGS)

        result = await orchestrator.run_analysis(SAMPLE_CONTENT_JSON, "casino review", debug_mode=False)

        self.assertTrue(result["success"])
        self.assertGreater(result["total_violations_found"], 0)
        self.assertIsInstance(result["report"], str)
        self.assertIn("YMYL Compliance Report", result["report"])

    async def test_h1_extracted_from_markdown_heading(self):
        """_build_analyzer_payload should read # heading from section content."""
        service = FakeService([empty_result(), empty_result(), empty_result()])
        orchestrator = AuditOrchestrator(service=service, settings=MINIMAL_SETTINGS)

        await orchestrator.run_analysis(SAMPLE_CONTENT_JSON, "casino review", debug_mode=False)

        # First call is a lens; its payload should contain the H1
        first_call_content = json.loads(service.calls[0]["content"])
        self.assertEqual(first_call_content["global_context"]["primary_topic"], "Sample Casino Review")

    async def test_verifier_failure_falls_back_to_candidates(self):
        failed = OpenAIResponseResult(success=False, status="failed", error_type="api_error", error_message="verifier down")
        service = FakeService([
            structured_result("Risk-free winnings"),
            empty_result(),
            empty_result(),
            failed,           # verifier fails
            structured_result("Risk-free winnings"),  # finalizer
        ])
        orchestrator = AuditOrchestrator(service=service, settings=MINIMAL_SETTINGS)

        result = await orchestrator.run_analysis(SAMPLE_CONTENT_JSON, "casino review", debug_mode=False)

        self.assertTrue(result["success"])
        self.assertGreater(result["unique_violations"], 0)

    async def test_debug_mode_returns_debug_info(self):
        service = FakeService([
            structured_result("Risk-free winnings"),
            empty_result(),
            empty_result(),
            empty_result(),   # verifier
            empty_result(),   # finalizer
        ])
        orchestrator = AuditOrchestrator(service=service, settings=MINIMAL_SETTINGS)

        result = await orchestrator.run_analysis(SAMPLE_CONTENT_JSON, "casino review", debug_mode=True)

        self.assertTrue(result["success"])
        self.assertIsNotNone(result["debug_info"])
        self.assertIn("detection", result["debug_info"])
        self.assertIn("verification", result["debug_info"])
        self.assertIn("finalization", result["debug_info"])


if __name__ == "__main__":
    unittest.main()
