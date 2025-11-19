
#!/usr/bin/env python3
"""
Base Feature Interface
Defines common interface for all analysis features (URL, HTML, etc.).
Refactored to remove redundant session logic and align with new Processor architecture.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional, List
import streamlit as st

class BaseAnalysisFeature(ABC):
    """Base class for all analysis features"""
    
    def __init__(self):
        """Initialize base feature"""
        # unique ID for UI keys (e.g., 'url_analysis')
        self.feature_id = self.__class__.__name__.lower().replace('analysisfeature', '').replace('feature', '')
        self.session_key_prefix = f"{self.feature_id}_"
    
    @abstractmethod
    def get_input_interface(self, disabled: bool = False) -> Dict[str, Any]:
        """
        Render input interface (text boxes, file uploaders).
        Args:
            disabled: Whether inputs should be disabled (e.g. during processing)
        Returns:
            Dict containing input data and validation status
        """
        pass
    
    @abstractmethod
    def extract_content(self, input_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Extract content from input.
        Returns:
            Tuple of (success, extracted_content_json, error_message)
        """
        pass
    
    @abstractmethod
    def get_feature_name(self) -> str:
        """Get display name for this feature"""
        pass
    
    @abstractmethod
    def get_source_description(self, input_data: Dict[str, Any]) -> str:
        """
        Get a short string describing the source (e.g., "example.com" or "report.html")
        Used for naming the final report file.
        """
        pass
    
    # --- Common Helpers ---

    def get_session_key(self, key: str) -> str:
        """Get prefixed session state key for UI widgets"""
        return f"{self.session_key_prefix}{key}"
    
    def validate_input(self, input_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Basic validation. Override in subclasses for specific checks.
        """
        if not input_data:
            return False, "No input data provided"
        if not input_data.get('is_valid', True):
            return False, input_data.get('error_message', 'Invalid input')
        return True, ""
    
    # --- Multi-File Hooks (Optional) ---
    
    def is_multi_file_input(self, input_data: Dict[str, Any]) -> bool:
        """Override to return True if this input contains multiple files"""
        return False

    def get_file_list(self, input_data: Dict[str, Any]) -> List[str]:
        """Override to return list of filenames if multi-file"""
        return []
    
    # --- Metrics ---

    def get_extraction_metrics(self, extracted_content: str) -> Dict[str, Any]:
        """Get basic metrics about extracted content for Admin view"""
        try:
            import json
            content_data = json.loads(extracted_content)
            big_chunks = content_data.get('big_chunks', [])
            
            total_small_chunks = sum(len(chunk.get('small_chunks', [])) for chunk in big_chunks)
            
            return {
                'big_chunks': len(big_chunks),
                'small_chunks': total_small_chunks,
                'json_size': len(extracted_content),
            }
        except Exception:
            return {
                'json_size': len(extracted_content) if extracted_content else 0,
                'error': "Could not parse JSON structure"
            }
