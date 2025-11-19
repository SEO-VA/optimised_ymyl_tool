#!/usr/bin/env python3
"""
URL Analysis Feature
Handles the UI and logic for analyzing web URLs.
Connects the UI input to the core URL extractor.
"""

import streamlit as st
from typing import Dict, Any, Tuple, Optional
from features.base_feature import BaseAnalysisFeature
from core.extractor import extract_url_content
from utils.helpers import validate_url, safe_log, extract_domain

class URLAnalysisFeature(BaseAnalysisFeature):
    """Feature for analyzing content from web URLs"""
    
    def get_feature_name(self) -> str:
        return "URL Analysis"
    
    def get_input_interface(self, disabled: bool = False) -> Dict[str, Any]:
        """Render simple URL input interface"""
        
        # URL input widget
        url = st.text_input(
            "**Enter URL:**",
            placeholder="https://example.com/page",
            key=self.get_session_key("url_input"),
            disabled=disabled,
            help="Enter the full URL including http:// or https://"
        )
        
        # Validation
        url = url.strip()
        is_valid = bool(url and validate_url(url))
        error_message = ""
        
        if url and not is_valid:
            error_message = "Invalid URL format (must start with http:// or https://)"
            st.warning(f"⚠️ {error_message}")
        
        return {
            'url': url,
            'is_valid': is_valid,
            'error_message': error_message
        }
    
    def extract_content(self, input_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Orchestrates extraction from the URL.
        Delegates actual work to core.extractor.extract_url_content
        """
        url = input_data.get('url', '')
        
        safe_log(f"URL Feature: Starting extraction for {url}")
        
        try:
            # Call the core logic
            success, extracted_content, error = extract_url_content(url)
            
            if success:
                safe_log(f"URL Feature: Extraction success ({len(extracted_content)} chars)")
                return True, extracted_content, None
            else:
                safe_log(f"URL Feature: Extraction failed - {error}")
                return False, None, error
                
        except Exception as e:
            error_msg = f"Unexpected error in URL feature: {str(e)}"
            safe_log(error_msg, "ERROR")
            return False, None, error_msg

    def get_source_description(self, input_data: Dict[str, Any]) -> str:
        """
        Returns a clean name for the report filename.
        Example: "example.com" instead of the full messy URL.
        """
        url = input_data.get('url', '')
        domain = extract_domain(url)
        if domain:
            return f"URL_{domain}"
        return "URL_Analysis"
