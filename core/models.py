#!/usr/bin/env python3
"""
Data Models Module
Defines the strict data structures (Blueprints) for the application.
Updated: Includes translation fields for multilingual support.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from enum import Enum

class Severity(str, Enum):
    """
    Severity levels strictly matching the Prompt's 'severity_framework'
    """
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def from_string(cls, value: str) -> 'Severity':
        """Safely convert AI string output to Enum, defaulting to MEDIUM if unknown."""
        try:
            if not value: return cls.MEDIUM
            return cls(value.lower().strip())
        except ValueError:
            return cls.MEDIUM

@dataclass
class Violation:
    """
    Represents a single violation object from the AI output.
    Updated to include Translation fields.
    """
    problematic_text: str
    violation_type: str
    explanation: str
    guideline_section: str
    page_number: Union[int, str]
    severity: Severity
    suggested_rewrite: str
    
    # --- NEW FIELDS FOR TRANSLATION SUPPORT ---
    translation: Optional[str] = None
    rewrite_translation: Optional[str] = None
    chunk_language: Optional[str] = "English"
    
    # Internal tracking (not from AI)
    source_audit_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert back to dictionary for JSON serialization"""
        return {
            "problematic_text": self.problematic_text,
            "violation_type": self.violation_type,
            "explanation": self.explanation,
            "guideline_section": self.guideline_section,
            "page_number": self.page_number,
            "severity": self.severity.value,
            "suggested_rewrite": self.suggested_rewrite,
            # Include new fields in dictionary output
            "translation": self.translation,
            "rewrite_translation": self.rewrite_translation,
            "chunk_language": self.chunk_language
        }

@dataclass
class AnalysisResult:
    """
    The final package returned by the Processor.
    """
    success: bool
    report: Optional[str] = None
    word_bytes: Optional[bytes] = None
    violations: List[Violation] = field(default_factory=list)
    raw_response: Optional[List[Any]] = None
    
    # Metrics
    processing_time: float = 0.0
    total_violations_found: int = 0
    unique_violations: int = 0  # Renamed to match common usage if needed
    
    # Error handling
    error: Optional[str] = None
    
    # Debug info
    debug_info: Optional[Dict[str, Any]] = None


@dataclass
class OpenAIResponseResult:
    """
    Structured transport result for Responses API calls.
    """

    success: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    status: Optional[str] = None
    output_text: Optional[str] = None
    raw_output_items: List[Dict[str, Any]] = field(default_factory=list)
    tool_summary: Dict[str, Any] = field(default_factory=dict)
    request_meta: Dict[str, Any] = field(default_factory=dict)
    parsed_payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "status": self.status,
            "output_text": self.output_text,
            "raw_output_items": self.raw_output_items,
            "tool_summary": self.tool_summary,
            "request_meta": self.request_meta,
            "parsed_payload": self.parsed_payload,
        }

@dataclass
class FileState:
    """
    Tracks the status of a single file in the UI.
    """
    filename: str
    status: str # 'pending', 'processing', 'complete', 'failed'
    result: Optional[AnalysisResult] = None
    start_time: Optional[float] = None
    error_message: Optional[str] = None
