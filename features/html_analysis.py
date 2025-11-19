#!/usr/bin/env python3
"""
HTML Analysis Feature
Updated: Passes casino_mode to extractor.
"""

import streamlit as st
import zipfile
import io
import json
from typing import Dict, Any, Tuple, Optional, List
from features.base_feature import BaseAnalysisFeature
from core.html_extractor import extract_html_content
from utils.helpers import safe_log, create_safe_filename

class HTMLAnalysisFeature(BaseAnalysisFeature):
    
    def get_feature_name(self) -> str:
        return "HTML Analysis"
    
    def get_input_interface(self, disabled: bool = False) -> Dict[str, Any]:
        input_method = st.radio(
            "**Input method:**",
            ["📁 Upload HTML/ZIP", "📝 Paste HTML"],
            horizontal=True,
            key=self.get_session_key("input_method"),
            disabled=disabled
        )
        
        input_data = {'input_method': input_method}
        is_valid = False
        error_message = ""
        
        if input_method == "📝 Paste HTML":
            html_content = st.text_area(
                "**Paste HTML Content:**",
                height=200,
                key=self.get_session_key("html_paste"),
                disabled=disabled
            )
            if html_content and len(html_content.strip()) > 10:
                is_valid = True
                input_data['html_content'] = html_content
                input_data['source_type'] = 'paste'
        else:
            uploaded_file = st.file_uploader(
                "**Upload HTML or ZIP:**",
                type=['zip', 'html', 'htm'],
                key=self.get_session_key("file_upload"),
                disabled=disabled
            )
            if uploaded_file:
                if uploaded_file.name.lower().endswith('.zip'):
                    try:
                        with zipfile.ZipFile(uploaded_file) as z:
                            if any(f.lower().endswith(('.html', '.htm')) for f in z.namelist()):
                                is_valid = True
                                input_data['source_type'] = 'zip'
                                input_data['zip_bytes'] = uploaded_file.getvalue()
                    except: pass
                else:
                    is_valid = True
                    input_data['source_type'] = 'html_file'
                    input_data['html_content'] = uploaded_file.getvalue().decode('utf-8', errors='ignore')
                input_data['filename'] = uploaded_file.name if uploaded_file else ""

        return {**input_data, 'is_valid': is_valid, 'error_message': error_message}

    def extract_content(self, input_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        source_type = input_data.get('source_type')
        # Retrieve flag injected by Layout
        casino_mode = input_data.get('casino_mode', False)
        
        if source_type == 'zip':
            return self._extract_zip_content(input_data['zip_bytes'], casino_mode)
        
        html_content = input_data.get('html_content', '')
        return extract_html_content(html_content, casino_mode)

    def _extract_zip_content(self, zip_bytes: bytes, casino_mode: bool) -> Tuple[bool, Optional[str], Optional[str]]:
        extracted_files = {}
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                file_list = [f for f in z.namelist() if f.lower().endswith(('.html', '.htm')) and not f.startswith('__MACOSX')]
                
                for filename in file_list:
                    try:
                        content = z.read(filename).decode('utf-8', errors='ignore')
                        success, json_content, _ = extract_html_content(content, casino_mode)
                        if success:
                            extracted_files[create_safe_filename(filename)] = json_content
                    except Exception: continue

            if not extracted_files: return False, None, "No valid HTML extracted"
            
            if len(extracted_files) == 1:
                return True, list(extracted_files.values())[0], None
                
            return True, json.dumps({"files": extracted_files}), None

        except Exception as e:
            return False, None, f"ZIP Error: {str(e)}"

    def is_multi_file_input(self, input_data: Dict[str, Any]) -> bool:
        return input_data.get('source_type') == 'zip'

    def get_file_list(self, input_data: Dict[str, Any]) -> List[str]:
        if self.is_multi_file_input(input_data): return ["Files inside ZIP"]
        return []

    def get_source_description(self, input_data: Dict[str, Any]) -> str:
        return input_data.get('filename', 'HTML_Content')
