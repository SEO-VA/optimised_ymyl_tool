#!/usr/bin/env python3
"""
OpenAI Service Module - Responses API
"""

import streamlit as st
from openai import AsyncOpenAI, BadRequestError
from typing import Optional, List, Dict, Any
from core.models import OpenAIResponseResult
from core.openai_contracts import ViolationsResponseSchema, STRUCTURED_OUTPUT_NAME
from utils.helpers import safe_log


STRUCTURED_OUTPUT_INSTRUCTIONS = """
Return only JSON that matches the configured response schema.
Place every finding inside the top-level "violations" array.
Do not wrap the JSON in markdown or add explanatory prose.
"""


class OpenAIService:
    def __init__(self, client: Optional[AsyncOpenAI] = None, model: Optional[str] = None, api_key: Optional[str] = None):
        self.client = client
        self.model = model
        self._config_error: Optional[str] = None

        if self.client is not None and self.model:
            return

        try:
            resolved_api_key = api_key or st.secrets["openai_api_key"]
            self.model = model or st.secrets["openai_model"]
            self.client = client or AsyncOpenAI(api_key=resolved_api_key)
        except KeyError as e:
            self._config_error = f"Missing OpenAI secret: {e}"
            safe_log(f"OpenAI Service: {self._config_error}", "CRITICAL")

    async def get_response(self,
                           content: str,
                           instructions: str,
                           task_name: str = "Audit",
                           timeout_seconds: int = 300,
                           vector_store_ids: Optional[List[str]] = None,
                           force_tool: bool = False) -> OpenAIResponseResult:
        """
        Uses the Responses API with structured outputs and detailed transport metadata.
        """
        config_error = self.validate_runtime_configuration(vector_store_ids=vector_store_ids)
        request_meta = self._build_request_meta(
            task_name=task_name,
            timeout_seconds=timeout_seconds,
            vector_store_ids=vector_store_ids,
            force_tool=force_tool,
            model=self.model,
        )
        if config_error:
            return OpenAIResponseResult(
                success=False,
                error_type="config_error",
                error_message=config_error,
                status="failed",
                request_meta=request_meta,
                tool_summary=self._empty_tool_summary(vector_store_ids=vector_store_ids, force_tool=force_tool),
            )

        model_candidates = self._get_model_candidates()
        try:
            for idx, candidate_model in enumerate(model_candidates):
                try:
                    response = await self.client.responses.create(
                        **self._build_call_args(
                            model=candidate_model,
                            content=content,
                            instructions=instructions,
                            timeout_seconds=timeout_seconds,
                            vector_store_ids=vector_store_ids,
                            force_tool=force_tool,
                        )
                    )
                    result = self._build_success_result(
                        response=response,
                        task_name=task_name,
                        request_meta=request_meta,
                        vector_store_ids=vector_store_ids,
                        force_tool=force_tool,
                    )
                    if idx > 0:
                        result.request_meta["model_fallback_used"] = candidate_model
                    return result
                except BadRequestError as e:
                    if idx < len(model_candidates) - 1 and self._should_retry_with_snapshot(e):
                        safe_log(f"{task_name}: Retrying with snapshot model after schema error: {e}", "WARNING")
                        continue
                    return self._build_exception_result(
                        task_name=task_name,
                        error_type="bad_request",
                        error_message=str(e),
                        request_meta=request_meta,
                        vector_store_ids=vector_store_ids,
                        force_tool=force_tool,
                    )
        except Exception as e:
            return self._build_exception_result(
                task_name=task_name,
                error_type="system_error",
                error_message=str(e),
                request_meta=request_meta,
                vector_store_ids=vector_store_ids,
                force_tool=force_tool,
            )

        return self._build_exception_result(
            task_name=task_name,
            error_type="unknown_error",
            error_message="No response returned from OpenAI client.",
            request_meta=request_meta,
            vector_store_ids=vector_store_ids,
            force_tool=force_tool,
        )

    def _build_json_input(self, content: str) -> str:
        """Make the payload intent explicit for the Responses API."""
        return f"JSON input payload:\n{content}"

    def validate_runtime_configuration(self, vector_store_ids: Optional[List[str]] = None) -> Optional[str]:
        if self._config_error:
            return self._config_error
        if not self.client:
            return "OpenAI client is not initialized."
        if not self.model:
            return "OpenAI model is not configured."
        if vector_store_ids is not None and not all(vs_id and str(vs_id).strip() for vs_id in vector_store_ids):
            return "One or more vector store IDs are missing or empty."
        return None

    def _build_call_args(self,
                         model: str,
                         content: str,
                         instructions: str,
                         timeout_seconds: int,
                         vector_store_ids: Optional[List[str]],
                         force_tool: bool) -> Dict[str, Any]:
        call_args: Dict[str, Any] = {
            "model": model,
            "instructions": self._normalize_instructions(instructions),
            "input": self._build_json_input(content),
            "text": {"format": self._structured_output_format()},
            "timeout": float(timeout_seconds),
        }

        if vector_store_ids:
            call_args["tools"] = [{"type": "file_search", "vector_store_ids": vector_store_ids}]
            call_args["include"] = ["file_search_call.results"]
            if force_tool:
                call_args["tool_choice"] = {"type": "file_search"}

        return call_args

    def _build_success_result(self,
                              response: Any,
                              task_name: str,
                              request_meta: Dict[str, Any],
                              vector_store_ids: Optional[List[str]],
                              force_tool: bool) -> OpenAIResponseResult:
        raw_output_items = self._serialize_output_items(getattr(response, "output", []))
        output_text = getattr(response, "output_text", None) or self._extract_output_text(getattr(response, "output", []))
        parsed_payload = self._parse_structured_output(output_text)
        tool_summary = self._build_tool_summary(
            output_items=getattr(response, "output", []),
            vector_store_ids=vector_store_ids,
            force_tool=force_tool,
        )

        request_meta = {
            **request_meta,
            "response_id": getattr(response, "id", None),
            "response_model": getattr(response, "model", None),
            "usage": self._serialize_model(getattr(response, "usage", None)),
        }

        status = getattr(response, "status", None)
        error = getattr(response, "error", None)
        error_message = getattr(error, "message", None) if error else None
        success = status == "completed" and (parsed_payload is not None or bool(output_text))
        error_type = None

        if not success:
            if error_message:
                error_type = "api_error"
            elif status == "incomplete":
                error_type = "incomplete_response"
                incomplete_details = getattr(response, "incomplete_details", None)
                error_message = self._serialize_model(incomplete_details) or "Response incomplete."
            elif not output_text:
                error_type = "empty_response"
                error_message = "Response completed without text output."
            else:
                error_type = "unexpected_status"
                error_message = f"Response status: {status}"

        if success:
            safe_log(f"{task_name}: Success ({len(output_text or '')} chars)")
        else:
            safe_log(f"{task_name}: Failed - {error_message}", "ERROR")

        return OpenAIResponseResult(
            success=success,
            error_type=error_type,
            error_message=error_message,
            status=status,
            output_text=output_text,
            raw_output_items=raw_output_items,
            tool_summary=tool_summary,
            request_meta=request_meta,
            parsed_payload=parsed_payload,
        )

    def _build_exception_result(self,
                                task_name: str,
                                error_type: str,
                                error_message: str,
                                request_meta: Dict[str, Any],
                                vector_store_ids: Optional[List[str]],
                                force_tool: bool) -> OpenAIResponseResult:
        safe_log(f"{task_name}: Exception - {error_message}", "ERROR")
        return OpenAIResponseResult(
            success=False,
            error_type=error_type,
            error_message=error_message,
            status="failed",
            tool_summary=self._empty_tool_summary(vector_store_ids=vector_store_ids, force_tool=force_tool),
            request_meta=request_meta,
        )

    def _structured_output_format(self) -> Dict[str, Any]:
        return {
            "type": "json_schema",
            "name": STRUCTURED_OUTPUT_NAME,
            "strict": True,
            "schema": ViolationsResponseSchema.model_json_schema(),
        }

    def _normalize_instructions(self, instructions: str) -> str:
        instructions = instructions.strip() if instructions else ""
        return f"{instructions}\n\n{STRUCTURED_OUTPUT_INSTRUCTIONS}".strip()

    def _parse_structured_output(self, output_text: Optional[str]) -> Optional[Dict[str, Any]]:
        if not output_text:
            return None
        try:
            return ViolationsResponseSchema.model_validate_json(output_text).model_dump(mode="json")
        except Exception as e:
            safe_log(f"OpenAI Service: Structured output parse failed, preserving raw text fallback. {e}", "WARNING")
            return None

    def _extract_output_text(self, output_items: List[Any]) -> Optional[str]:
        fragments: List[str] = []
        for item in output_items or []:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []):
                if getattr(content, "type", None) == "output_text" and getattr(content, "text", None):
                    fragments.append(content.text)
        if not fragments:
            return None
        return "\n".join(fragments)

    def _serialize_output_items(self, output_items: List[Any]) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for item in output_items or []:
            dumped = self._serialize_model(item)
            if isinstance(dumped, dict):
                serialized.append(dumped)
            else:
                serialized.append({"type": getattr(item, "type", "unknown"), "value": dumped})
        return serialized

    def _serialize_model(self, value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    def _build_tool_summary(self,
                            output_items: List[Any],
                            vector_store_ids: Optional[List[str]],
                            force_tool: bool) -> Dict[str, Any]:
        summary = self._empty_tool_summary(vector_store_ids=vector_store_ids, force_tool=force_tool)

        for item in output_items or []:
            if getattr(item, "type", None) != "file_search_call":
                continue
            summary["file_search_used"] = True
            summary["file_search_calls"] += 1
            summary["file_search_statuses"].append(getattr(item, "status", None))
            summary["file_search_queries"].extend(getattr(item, "queries", []) or [])
            summary["file_search_result_count"] += len(getattr(item, "results", []) or [])

        return summary

    def _empty_tool_summary(self, vector_store_ids: Optional[List[str]], force_tool: bool) -> Dict[str, Any]:
        return {
            "requested_tools": ["file_search"] if vector_store_ids else [],
            "tool_choice": "forced_file_search" if force_tool and vector_store_ids else "auto",
            "file_search_used": False,
            "file_search_calls": 0,
            "file_search_statuses": [],
            "file_search_queries": [],
            "file_search_result_count": 0,
        }

    def _build_request_meta(self,
                            task_name: str,
                            timeout_seconds: int,
                            vector_store_ids: Optional[List[str]],
                            force_tool: bool,
                            model: Optional[str]) -> Dict[str, Any]:
        return {
            "task_name": task_name,
            "model": model,
            "timeout_seconds": timeout_seconds,
            "structured_output": STRUCTURED_OUTPUT_NAME,
            "vector_store_ids": vector_store_ids or [],
            "force_tool": force_tool,
        }

    def _get_model_candidates(self) -> List[str]:
        if not self.model:
            return []
        if self.model == "gpt-4o":
            return ["gpt-4o", "gpt-4o-2024-08-06"]
        return [self.model]

    def _should_retry_with_snapshot(self, error: BadRequestError) -> bool:
        message = str(error).lower()
        markers = ("json_schema", "structured output", "response format", "text.format")
        return any(marker in message for marker in markers)

openai_service = OpenAIService()
