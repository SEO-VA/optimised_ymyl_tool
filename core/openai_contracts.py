#!/usr/bin/env python3
"""
OpenAI response contracts used for structured outputs.
"""

from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ViolationSchema(BaseModel):
    """Structured output schema for a single violation."""

    model_config = ConfigDict(extra="forbid")

    problematic_text: str
    violation_type: str
    explanation: str
    guideline_section: str
    page_number: Union[int, str]
    severity: str
    suggested_rewrite: str
    translation: Optional[str]
    rewrite_translation: Optional[str]
    chunk_language: str


class ViolationsResponseSchema(BaseModel):
    """Top-level structured output schema for analyzer and deduplicator runs."""

    model_config = ConfigDict(extra="forbid")

    violations: List[ViolationSchema]


STRUCTURED_OUTPUT_NAME = "ymyl_violation_list"
