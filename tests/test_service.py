#!/usr/bin/env python3

import unittest
from types import SimpleNamespace

from core.service import OpenAIService


class FakeModel(SimpleNamespace):
    def model_dump(self, mode="json"):
        def convert(value):
            if isinstance(value, list):
                return [convert(item) for item in value]
            if hasattr(value, "model_dump"):
                return value.model_dump(mode=mode)
            return value

        return {key: convert(value) for key, value in self.__dict__.items()}


class FakeResponsesClient:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class FakeClient:
    def __init__(self, response):
        self.responses = FakeResponsesClient(response)


def make_message_output(text):
    return FakeModel(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[FakeModel(type="output_text", text=text, annotations=[])],
    )


def make_file_search_call():
    return FakeModel(
        id="fs_1",
        type="file_search_call",
        status="completed",
        queries=["ymyl policy"],
        results=[FakeModel(file_id="file_1", filename="guide.pdf", score=0.99, text="policy")],
    )


def make_response(status="completed", output_text=None, output=None, error=None):
    return FakeModel(
        id="resp_1",
        status=status,
        output_text=output_text,
        output=output or [],
        error=error,
        model="gpt-4o",
        usage=FakeModel(input_tokens=10, output_tokens=20, total_tokens=30),
    )


class OpenAIServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_response_with_valid_structured_output(self):
        payload = '{"violations": [{"problematic_text": "Risk-free winnings", "violation_type": "Misleading claim", "explanation": "Guarantee language is not allowed.", "guideline_section": "4.2", "page_number": 3, "severity": "critical", "suggested_rewrite": "Avoid guarantee language.", "translation": null, "rewrite_translation": null, "chunk_language": "English"}]}'
        response = make_response(output_text=payload, output=[make_message_output(payload)])
        client = FakeClient(response)
        service = OpenAIService(client=client, model="gpt-4o")

        result = await service.get_response("{}", "Return JSON", task_name="Audit #1")

        self.assertTrue(result.success)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.parsed_payload["violations"][0]["severity"], "critical")
        self.assertEqual(client.responses.last_kwargs["text"]["format"]["type"], "json_schema")

    async def test_completed_response_with_empty_output_text_uses_output_items(self):
        payload = '{"violations": []}'
        response = make_response(output_text="", output=[make_message_output(payload)])
        service = OpenAIService(client=FakeClient(response), model="gpt-4o")

        result = await service.get_response("{}", "Return JSON", task_name="Audit #1")

        self.assertTrue(result.success)
        self.assertEqual(result.output_text, payload)
        self.assertEqual(result.parsed_payload, {"violations": []})

    async def test_failed_response_surfaces_error(self):
        error = FakeModel(message="Model failed to complete.")
        response = make_response(status="failed", output_text="", output=[], error=error)
        service = OpenAIService(client=FakeClient(response), model="gpt-4o")

        result = await service.get_response("{}", "Return JSON", task_name="Audit #1")

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "api_error")
        self.assertIn("Model failed", result.error_message)

    async def test_file_search_summary_is_captured(self):
        payload = '{"violations": []}'
        response = make_response(
            output_text=payload,
            output=[make_file_search_call(), make_message_output(payload)],
        )
        client = FakeClient(response)
        service = OpenAIService(client=client, model="gpt-4o")

        result = await service.get_response(
            "{}",
            "Return JSON",
            task_name="Audit #1",
            vector_store_ids=["vs_123"],
            force_tool=True,
        )

        self.assertTrue(result.success)
        self.assertTrue(result.tool_summary["file_search_used"])
        self.assertEqual(result.tool_summary["file_search_result_count"], 1)
        self.assertEqual(client.responses.last_kwargs["tool_choice"], {"type": "file_search"})
        self.assertEqual(client.responses.last_kwargs["include"], ["file_search_call.results"])


if __name__ == "__main__":
    unittest.main()
