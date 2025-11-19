#!/usr/bin/env python3
"""
URL Analysis Feature
Updated: Passes casino_mode to extractor.
"""

import streamlit as st
from typing import Dict, Any, Tuple, Optional
from features.base_feature import BaseAnalysisFeature
from core.extractor import extract_url_content
from utils.helpers import validate_url, safe_log, extract_domain

class URLAnalysisFeature(BaseAnalysisFeature):
    
    def get_feature_name(self) -> str:
        return "URL Analysis"
    
    def get_input_interface(self, disabled: bool = False) -> Dict[str, Any]:
        url = st.text_input(
            "**Enter URL:**",
            placeholder="https://example.com/page",
            key=self.get_session_key("url_input"),
            disabled=disabled
        )
        
        url = url.strip()
        is_valid = bool(url and validate_url(url))
        error_message = "Invalid URL format" if (url and not is_valid) else ""
        
        return {
            'url': url,
            'is_valid': is_valid,
            'error_message': error_message
        }
    
    def extract_content(self, input_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        url = input_data.get('url', '')
        # Retrieve flag injected by Admin/User Layout
        casino_mode = input_data.get('casino_mode', False)
        
        return extract_url_content(url, casino_mode)

    def get_source_description(self, input_data: Dict[str, Any]) -> str:
        url = input_data.get('url', '')
        domain = extract_domain(url)
        return f"URL_{domain}" if domain else "URL_Analysis"
