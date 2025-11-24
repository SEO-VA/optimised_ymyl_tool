#!/usr/bin/env python3
"""
HTML Analysis Feature - ZIP & Single File Support
Handles the input interface for HTML files.
- Supports Google Doc ZIP exports (finds the .html inside).
- Supports bulk analysis (multiple .html files in one ZIP).
- Connects to the Smart Switch extractor.
"""

import streamlit as st
import zipfile
import io
import json
import os
from typing import Dict, Any, Tuple, Optional, List
from features.base_feature import BaseAnalysisFeature
from core.html_extractor import extract_html_content
from utils.helpers import safe_log, create_safe_filename

class HTMLAnalysisFeature(BaseAnalysisFeature):
    
    def get_feature_name(self) -> str:
        return "HTML Analysis"
    
    def get_input_interface(self, disabled: bool = False) -> Dict[str, Any]:
        # 1. Input Method Toggle
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
        
        # 2. Paste Interface
        if input_method == "📝 Paste HTML":
            html_content = st.text_area(
                "**Paste HTML Content:**",
                height=200,
                placeholder="<html>...</html>",
                key=self.get_session_key("html_paste"),
                disabled=disabled,
                help="Paste the raw source code here."
            )
            if html_content and len(html_content.strip()) > 10:
                is_valid = True
                input_data['html_content'] = html_content
                input_data['source_type'] = 'paste'
            elif html_content:
                error_message = "Content too short."

        # 3. Upload Interface (ZIP / HTML)
        else:
            uploaded_file = st.file_uploader(
                "**Upload HTML or ZIP:**",
                type=['zip', 'html', 'htm'],
                key=self.get_session_key("file_upload"),
                disabled=disabled,
                help="Upload a single HTML file or a Google Doc ZIP export."
            )
            
            if uploaded_file:
                input_data['filename'] = uploaded_file.name
                
                # Handle ZIP
                if uploaded_file.name.lower().endswith('.zip'):
                    try:
                        # Peek inside to validate
                        with zipfile.ZipFile(uploaded_file) as z:
                            # Look for any HTML file, ignoring MAC system files
                            valid_files = [
                                f for f in z.namelist() 
                                if f.lower().endswith(('.html', '.htm')) 
                                and not f.startswith('__MACOSX') 
                                and not f.startswith('.')
                            ]
                            
                            if valid_files:
                                is_valid = True
                                input_data['source_type'] = 'zip'
                                input_data['zip_bytes'] = uploaded_file.getvalue()
                                input_data['file_count'] = len(valid_files)
                            else:
                                error_message = "No .html files found inside ZIP."
                    except Exception as e:
                        error_message = f"Invalid ZIP file: {str(e)}"
                
                # Handle Single HTML
                else:
                    is_valid = True
                    input_data['source_type'] = 'html_file'
                    try:
                        input_data['html_content'] = uploaded_file.getvalue().decode('utf-8', errors='ignore')
                    except Exception as e:
                        is_valid = False
                        error_message = f"Read error: {str(e)}"

        return {
            **input_data,
            'is_valid': is_valid,
            'error_message': error_message
        }

    def extract_content(self, input_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Orchestrates extraction.
        Passes 'casino_mode' to the core extractor so it knows whether to use Surgical or Generic logic.
        """
        source_type = input_data.get('source_type')
        casino_mode = input_data.get('casino_mode', False) # Injected by Layout
        
        # A. Handle ZIP (Google Docs or Bulk)
        if source_type == 'zip':
            return self._extract_zip_content(input_data['zip_bytes'], casino_mode)
        
        # B. Handle Single Text (Paste or File)
        html_content = input_data.get('html_content', '')
        safe_log(f"HTML Feature: Extracting single file (Casino Mode: {casino_mode})")
        return extract_html_content(html_content, casino_mode)

    def _extract_zip_content(self, zip_bytes: bytes, casino_mode: bool) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Unzips the archive in memory and processes valid HTML files.
        """
        extracted_files = {}
        
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                # Filter for actual content files (ignore folders/system files)
                file_list = [
                    f for f in z.namelist() 
                    if f.lower().endswith(('.html', '.htm')) 
                    and not f.startswith('__MACOSX')
                    and not f.startswith('.')
                ]
                
                safe_log(f"HTML Feature: Found {len(file_list)} HTML files in ZIP.")
                
                for filename in file_list:
                    try:
                        # Read HTML
                        content = z.read(filename).decode('utf-8', errors='ignore')
                        
                        # SEND TO SMART SWITCH (extract_html_content)
                        # This will detect if it's a Google Doc or Web Page and route accordingly
                        success, json_content, _ = extract_html_content(content, casino_mode)
                        
                        if success:
                            # Use safe filename (remove directory paths)
                            clean_name = create_safe_filename(os.path.basename(filename))
                            extracted_files[clean_name] = json_content
                            safe_log(f"Successfully extracted: {filename}")
                            
                    except Exception as e:
                        safe_log(f"Skipping file {filename}: {e}", "WARNING")

            if not extracted_files:
                return False, None, "No valid HTML content could be extracted from ZIP"

            # Result Packaging:
            # If 1 file -> Return as Single Analysis (Cleanest for Google Docs)
            if len(extracted_files) == 1:
                single_key = list(extracted_files.keys())[0]
                return True, extracted_files[single_key], None

            # If >1 file -> Return as Multi-File Batch
            return True, json.dumps({"files": extracted_files}), None

        except Exception as e:
            return False, None, f"ZIP Processing Error: {str(e)}"

    # --- Multi-File Hooks ---

    def is_multi_file_input(self, input_data: Dict[str, Any]) -> bool:
        """
        Returns True only if the ZIP actually contained >1 valid HTML file.
        Google Docs usually have 1 file, so we treat them as Single Mode.
        """
        return input_data.get('source_type') == 'zip' and input_data.get('file_count', 0) > 1

    def get_file_list(self, input_data: Dict[str, Any]) -> List[str]:
        if self.is_multi_file_input(input_data):
            count = input_data.get('file_count', 0)
            return [f"{count} HTML files found in archive"]
        return []

    def get_source_description(self, input_data: Dict[str, Any]) -> str:
        return input_data.get('filename', 'HTML_Content')
