#!/usr/bin/env python3
"""
Admin Layout
Advanced interface with Debug Mode and Test Mode (1 vs 5 audits).
"""

import streamlit as st
from utils.feature_registry import FeatureRegistry
from core.processor import processor
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
        
        col1, col2 = st.columns([3, 1])
        with col1:
            if self.current_step == 1:
                self._render_step1(feature_handler)
            else:
                self._render_step2(feature_handler)
        with col2:
            if st.button("🔄 Reset Admin"):
                st.session_state.clear()
                st.rerun()

    def _render_step1(self, handler):
        st.subheader("Step 1: Extraction")
        input_data = handler.get_input_interface()
        is_multi = handler.is_multi_file_input(input_data) if hasattr(handler, 'is_multi_file_input') else False
        
        if st.button("Extract", disabled=not input_data.get('is_valid')):
            success, content, err = handler.extract_content(input_data)
            if success:
                if is_multi:
                    st.session_state['admin_multi_extracted'] = content
                else:
                    st.session_state['extracted_content'] = content
                    st.session_state['source_info'] = handler.get_source_description(input_data)
                st.rerun()
            else:
                st.error(err)

    def _render_step2(self, handler):
        st.subheader("Step 2: Analysis")
        
        # Toggles
        col1, col2 = st.columns(2)
        debug = col1.checkbox("Debug Mode", value=True)
        test_mode = col2.checkbox("Test Mode (1 Audit)", value=False)
        audit_count = 1 if test_mode else 5
        
        is_multi = 'admin_multi_extracted' in st.session_state
        
        if st.button(f"Run Analysis ({audit_count} Audits)", type="primary"):
            if is_multi:
                self._run_multi(st.session_state['admin_multi_extracted'], debug, audit_count)
            else:
                self._run_single(st.session_state['extracted_content'], st.session_state['source_info'], debug, audit_count)

    def _run_single(self, content, source, debug, count):
        with st.status("Analyzing...") as status:
            result = processor.process_single_file(content, source, False, debug, count)
            if result['success']:
                status.update(label="Done", state="complete")
                if debug and result.get('debug_mode'):
                    # Simple debug view if component missing
                    st.json(result.get('violations', []))
                st.markdown(result['report'])
            else:
                st.error(result.get('error'))

    def _run_multi(self, content_json, debug, count):
        files = json.loads(content_json).get('files', {})
        with st.status(f"Analyzing {len(files)} files...") as status:
            results = processor.process_multi_file(files, False, debug, count)
            status.update(label="Done", state="complete")
            
            for fname, res in results.items():
                with st.expander(f"{fname} ({'Success' if res['success'] else 'Failed'})"):
                    if res['success']:
                        st.markdown(res['report'])
                    else:
                        st.error(res.get('error'))
