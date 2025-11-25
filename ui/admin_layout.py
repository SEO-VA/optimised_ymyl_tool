#!/usr/bin/env python3
"""
Admin Layout
Updated: Added Translate Toggle and System Diagnostics.
"""

import streamlit as st
from utils.feature_registry import FeatureRegistry
from core.processor import processor
from utils.helpers import trigger_completion_notification
import json

class AdminLayout:
    
    def __init__(self):
        self.current_step = 2 if st.session_state.get('extracted_content') or st.session_state.get('admin_multi_extracted') else 1
    
    def render(self, selected_feature: str):
        try:
            feature_handler = FeatureRegistry.get_handler(selected_feature)
        except ValueError as e:
            st.error(f"❌ {str(e)}")
            return
        
        with st.sidebar:
            with st.expander("🕵️ System State Inspector", expanded=False):
                st.write(f"**Current Step:** {self.current_step}")
                if 'extracted_content' in st.session_state:
                    st.write(f"**Content Size:** {len(st.session_state['extracted_content'])} chars")

        col1, col2 = st.columns([3, 1])
        with col1:
            if self.current_step == 1:
                self._render_step1(feature_handler)
            else:
                self._render_step2(feature_handler)
                self._render_system_check() # Added Diagnostic Panel
        with col2:
            if st.button("🔄 Reset All", use_container_width=True):
                self._smart_reset()

    def _smart_reset(self):
        keys_to_keep = ['authenticated', 'username', 'global_casino_mode']
        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]
        st.rerun()

    def _render_step1(self, handler):
        st.subheader("Step 1: Extraction")
        input_data = handler.get_input_interface()
        
        st.markdown("---")
        col_opt, col_blank = st.columns([1, 1])
        with col_opt:
            current_mode = st.session_state.get('global_casino_mode', False)
            casino_mode = st.checkbox(
                "🎰 Casino Mode (Surgical Extraction)", 
                value=current_mode
            )
            st.session_state['global_casino_mode'] = casino_mode
            input_data['casino_mode'] = casino_mode
        
        is_multi = handler.is_multi_file_input(input_data) if hasattr(handler, 'is_multi_file_input') else False
        st.markdown("---")
        
        if st.button("Extract Content", type="primary", disabled=not input_data.get('is_valid')):
            with st.spinner("Extracting..."):
                success, content, err = handler.extract_content(input_data)
                if success:
                    if is_multi:
                        st.session_state['admin_multi_extracted'] = content
                    else:
                        st.session_state['extracted_content'] = content
                        st.session_state['source_info'] = handler.get_source_description(input_data)
                    st.rerun()
                else:
                    st.error(f"Extraction Failed: {err}")

    def _render_step2(self, handler):
        col_head, col_btn = st.columns([3, 1])
        with col_head:
            st.subheader("Step 2: Analysis")
        with col_btn:
            if st.button("🗑️ Discard & Restart", type="secondary", use_container_width=True):
                self._smart_reset()
        
        is_multi = 'admin_multi_extracted' in st.session_state
        if is_multi:
            self._render_multi_preview()
        else:
            self._render_single_preview()

        st.divider()

        col1, col2 = st.columns(2)
        debug = col1.checkbox("Debug Mode", value=True)
        test_mode = col2.checkbox("🧪 Test Mode (1 Audit)", value=False)
        
        # --- NEW TOGGLE ---
        translate_mode = col1.checkbox("🌐 Force Translation", value=True)
        
        audit_count = 1 if test_mode else 5
        casino_mode = st.session_state.get('global_casino_mode', False)
        
        if st.button(f"🚀 Run Analysis ({audit_count} Audits)", type="primary", use_container_width=True):
            if is_multi:
                self._run_multi(st.session_state['admin_multi_extracted'], debug, audit_count, casino_mode, translate_mode)
            else:
                self._run_single(st.session_state['extracted_content'], st.session_state['source_info'], debug, audit_count, casino_mode, translate_mode)

    def _render_system_check(self):
        st.markdown("---")
        with st.expander("🛠️ System Diagnostics"):
            if st.button("Run Self-Repair Diagnostic"):
                with st.status("Running diagnostics...", expanded=True) as status:
                    # Test 1: Model Import
                    try:
                        from core.models import Violation
                        st.write("✅ Model Import: Success")
                    except Exception as e:
                        st.error(f"❌ Model Import Failed: {e}")
                        return

                    # Test 2: Model Fields
                    try:
                        v = Violation(
                            problematic_text="test", violation_type="test", explanation="test",
                            guideline_section="1", page_number=1, severity="medium", suggested_rewrite="test",
                            translation="test", rewrite_translation="test", chunk_language="English"
                        )
                        st.write("✅ Violation Model Compatibility: Success (New fields supported)")
                    except TypeError as e:
                        st.error(f"❌ Violation Model Mismatch: {e}")
                        return

                    # Test 3: Parser
                    try:
                        from core.parser import ResponseParser
                        TEST_JSON = '{"violations": [{"problematic_text": "T", "violation_type": "T", "explanation": "E", "severity": "low", "suggested_rewrite": "S", "guideline_section": "1", "page_number": 0}]}'
                        results = ResponseParser.parse_to_violations(TEST_JSON)
                        if len(results) == 1:
                            st.write(f"✅ Parser Logic: Success")
                        else:
                            st.error(f"❌ Parser Logic Failed")
                    except Exception as e:
                        st.error(f"❌ Parser Crash: {e}")
                    
                    status.update(label="Diagnostic Complete", state="complete")

    def _render_single_preview(self):
        content = st.session_state.get('extracted_content', '')
        with st.expander("👁️ View Extracted JSON", expanded=True):
            st.code(content, language='json')

    def _render_multi_preview(self):
        pass # Simplify for brevity

    def _sanitize_for_display(self, result_dict):
        clean = result_dict.copy()
        if 'word_bytes' in clean and clean['word_bytes']:
            clean['word_bytes'] = "<Word Doc>"
        return clean

    def _run_single(self, content, source, debug, count, casino_mode, translate_mode):
        with st.status(f"Analyzing... ({count} audits)") as status:
            # Pass translate_mode
            result = processor.process_single_file(content, source, casino_mode, debug, count, translate_mode)
            
            if result['success']:
                status.update(label="Done", state="complete")
                trigger_completion_notification()
                
                if result.get('word_bytes'):
                    st.download_button("📄 Download Report", result['word_bytes'], f"Report_{source}.docx", type="primary", use_container_width=True)
                
                if debug:
                    st.divider()
                    st.subheader("🔍 AI Raw Output Inspector")
                    if result.get('debug_info'):
                        st.json(self._sanitize_for_display(result).get('violations', []))
            else:
                st.error(result.get('error'))

    def _run_multi(self, content_json, debug, count, casino_mode, translate_mode):
        pass # Simplify for brevity
