#!/usr/bin/env python3
"""
Data Models Module
Defines the strict data structures (Blueprints) that mirror the AI Prompt.
Ensures type safety and strictly enforces the schema defined in the System 2 prompt.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from enum import Enum

class Severity(str, Enum):
    """
    Severity levels strictly matching the Prompt's 'severity_framework'
    Plus 'HIGH' for legacy compatibility if needed.
    """
    CRITICAL = "critical"
    HIGH = "high"       # Included for backward compatibility with reporter.py emojis
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def from_string(cls, value: str) -> 'Severity':
        """Safely convert AI string output to Enum, defaulting to MEDIUM if unknown."""
        try:
            return cls(value.lower().strip())
        except ValueError:
            return cls.MEDIUM

@dataclass
class Violation:
    """
    Represents a single violation object from the AI output.
    Strictly maps to the 'violations' object in your JSON Prompt.
    """
    problematic_text: str
    violation_type: str
    explanation: str
    guideline_section: str
    page_number: Union[int, str] # Handles "12" or 12
    severity: Severity
    suggested_rewrite: str
    
    # Optional fields for multilingual support (defined in prompt validation rules)
    translation: Optional[str] = None
    rewrite_translation: Optional[str] = None
    chunk_language: Optional[str] = "English"
    
    # Internal tracking fields (not from AI, but needed for Logic)
    source_audit_id: Optional[int] = None # Which of the 5 audits found this?

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
            "translation": self.translation,
            "rewrite_translation": self.rewrite_translation,
            "chunk_language": self.chunk_language
        }

@dataclass
class AnalysisResult:
    """
    The final package returned by the Processor.
    Replaces the generic dictionary previously used in analyzer.py
    """
    success: bool
    report: Optional[str] = None         # The Markdown report
    word_bytes: Optional[bytes] = None   # The generated Docx
    violations: List[Violation] = field(default_factory=list) # Structured data
    raw_response: Optional[List[Any]] = None # The raw JSON from AI (for Debug)
    
    # Metrics
    processing_time: float = 0.0
    total_violations_found: int = 0      # Before deduplication
    unique_violations_count: int = 0     # After deduplication
    
    # Error handling
    error: Optional[str] = None
    
    @property
    def is_complete(self) -> bool:
        return self.success and self.report is not None

@dataclass
class FileState:
    """
    Tracks the status of a single file in the UI.
    Replaces 'multi_{filename}_status' strings.
    """
    filename: str
    status: str # 'pending', 'processing', 'complete', 'failed'
    result: Optional[AnalysisResult] = None
    start_time: Optional[float] = None
    error_message: Optional[str] = None
