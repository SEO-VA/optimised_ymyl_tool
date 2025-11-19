#!/usr/bin/env python3
"""
HTML Analysis Feature
Handles UI and Logic for HTML inputs (Paste, File Upload, ZIP Archive).
Supports both Single-File and Multi-File (Batch) modes.
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
    """Feature for analyzing content from HTML files or ZIP archives"""
    
    def get_feature_name(self) -> str:
        return "HTML Analysis"
    
    def get_input_interface(self, disabled: bool = False) -> Dict[str, Any]:
        """Render HTML input options (Paste vs Upload)"""
        
        # Input method selection
        input_method = st.radio(
            "**Input method:**",
            ["📁 Upload HTML/ZIP", "📝 Paste HTML"],
            horizontal=True,
            key=self.get_session_key("input_method"),
            disabled=disabled
        )
        
        input_data = {'input_method': input_method}
        error_message = ""
        is_valid = False
        
        if input_method == "📝 Paste HTML":
            # Paste Interface
            html_content = st.text_area(
                "**Paste HTML Content:**",
                height=200,
                placeholder="<html><body>...</body></html>",
                key=self.get_session_key("html_paste"),
                disabled=disabled
            )
            if html_content and len(html_content.strip()) > 10:
                is_valid = True
                input_data['html_content'] = html_content
                input_data['source_type'] = 'paste'
            elif html_content:
                error_message = "HTML content too short"

        else:
            # File Upload Interface
            uploaded_file = st.file_uploader(
                "**Upload HTML or ZIP:**",
                type=['zip', 'html', 'htm'],
                key=self.get_session_key("file_upload"),
                disabled=disabled,
                help="Upload a single HTML file or a ZIP containing multiple HTML files"
            )
            
            if uploaded_file:
                input_data['uploaded_file'] = uploaded_file
                input_data['filename'] = uploaded_file.name
                
                if uploaded_file.name.lower().endswith('.zip'):
                    # Pre-validate ZIP
                    try:
                        with zipfile.ZipFile(uploaded_file) as z:
                            html_files = [f for f in z.namelist() if f.lower().endswith(('.html', '.htm')) and not f.startswith('__MACOSX')]
                            if html_files:
                                is_valid = True
                                input_data['source_type'] = 'zip'
                                input_data['file_count'] = len(html_files)
                                input_data['zip_bytes'] = uploaded_file.getvalue()
                            else:
                                error_message = "No HTML files found in ZIP"
                    except Exception:
                        error_message = "Invalid ZIP file"
                else:
                    # Single HTML file
                    is_valid = True
                    input_data['source_type'] = 'html_file'
                    input_data['html_content'] = uploaded_file.getvalue().decode('utf-8', errors='ignore')

        return {
            **input_data,
            'is_valid': is_valid,
            'error_message': error_message
        }

    def extract_content(self, input_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Extracts content. 
        If ZIP with multiple files -> Returns JSON with 'files' key.
        If Single file -> Returns standard extraction JSON.
        """
        source_type = input_data.get('source_type')
        
        if source_type == 'zip':
            return self._extract_zip_content(input_data['zip_bytes'])
        
        # Single file logic (Paste or Upload)
        html_content = input_data.get('html_content', '')
        return extract_html_content(html_content)

    def _extract_zip_content(self, zip_bytes: bytes) -> Tuple[bool, Optional[str], Optional[str]]:
        """Handle ZIP extraction logic"""
        extracted_files = {}
        
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                # Filter for valid HTML files
                file_list = [f for f in z.namelist() 
                           if f.lower().endswith(('.html', '.htm')) 
                           and not f.startswith('__MACOSX/')
                           and not f.endswith('/')] # skip directories
                
                safe_log(f"HTML Feature: Found {len(file_list)} files in ZIP")
                
                for filename in file_list:
                    try:
                        # Read and decode
                        content = z.read(filename).decode('utf-8', errors='ignore')
                        
                        # Extract using core extractor
                        success, json_content, error = extract_html_content(content)
                        
                        if success:
                            # Store with clean filename
                            clean_name = create_safe_filename(filename)
                            extracted_files[clean_name] = json_content
                    except Exception as e:
                        safe_log(f"Skipping file {filename}: {e}")

            if not extracted_files:
                return False, None, "No valid HTML content could be extracted from ZIP"

            # If only 1 file succeeded, treat as single file mode
            if len(extracted_files) == 1:
                single_content = list(extracted_files.values())[0]
                return True, single_content, None

            # Multi-file mode: Package into special structure for Processor
            master_json = json.dumps({"files": extracted_files})
            return True, master_json, None

        except Exception as e:
            return False, None, f"ZIP Processing Error: {str(e)}"

    # --- Multi-File Hooks ---

    def is_multi_file_input(self, input_data: Dict[str, Any]) -> bool:
        """Return True if this is a ZIP with >1 file"""
        return input_data.get('source_type') == 'zip' and input_data.get('file_count', 0) > 1

    def get_file_list(self, input_data: Dict[str, Any]) -> List[str]:
        """Return mock list of files for UI (since we haven't unpacked ZIP yet)"""
        if self.is_multi_file_input(input_data):
            count = input_data.get('file_count', 0)
            return [f"File {i+1} (inside ZIP)" for i in range(count)]
        return []

    def get_source_description(self, input_data: Dict[str, Any]) -> str:
        """Return filename or generic description"""
        if input_data.get('filename'):
            return input_data['filename']
        return "HTML_Content"
