#!/usr/bin/env python3
"""
Admin Layout
Advanced interface with Debug Mode, Test Mode, and Data Preview.
Updated: Added 'Extracted Data Preview' section in Step 2.
"""

import streamlit as st
from utils.feature_registry import FeatureRegistry
from core.processor import processor
import json

class AdminLayout:
    
    def __init__(self):
        # Determine current step
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
        
        # --- NEW: PREVIEW SECTION ---
        st.info("👇 Check the extracted data below before running AI.")
        
        is_multi = 'admin_multi_extracted' in st.session_state
        
        if is_multi:
            content_json = st.session_state['admin_multi_extracted']
            try:
                files = json.loads(content_json).get('files', {})
                file_list = list(files.keys())
                
                col_sel, col_len = st.columns([3, 1])
                with col_sel:
                    preview_file = st.selectbox("Select file to inspect:", file_list)
                with col_len:
                    if preview_file:
                        st.caption(f"Size: {len(files[preview_file])} chars")
                
                if preview_file:
                    with st.expander(f"👁️ View JSON: {preview_file}", expanded=False):
                        st.code(files[preview_file], language='json')
            except json.JSONDecodeError:
                st.error("Failed to parse multi-file JSON for preview")
        else:
            content = st.session_state['extracted_content']
            with st.expander("👁️ View Extracted JSON Payload", expanded=False):
                st.caption(f"Total Size: {len(content)} characters")
                st.code(content, language='json')

        st.divider()

        # --- Analysis Controls ---
        col1, col2 = st.columns(2)
        debug = col1.checkbox("Debug Mode", value=True)
        test_mode = col2.checkbox("Test Mode (1 Audit)", value=False)
        audit_count = 1 if test_mode else 5
        
        if st.button(f"🚀 Run Analysis ({audit_count} Audits)", type="primary"):
            if is_multi:
                self._run_multi(st.session_state['admin_multi_extracted'], debug, audit_count)
            else:
                self._run_single(st.session_state['extracted_content'], st.session_state['source_info'], debug, audit_count)

    def _run_single(self, content, source, debug, count):
        with st.status(f"Analyzing... ({count} audits)") as status:
            result = processor.process_single_file(
                content=content, 
                source_description=source, 
                casino_mode=False, 
                debug_mode=debug, 
                audit_count=count
            )
            
            if result['success']:
                status.update(label="Done", state="complete")
                
                if result.get('word_bytes'):
                    st.download_button(
                        label="📄 Download Word Report", 
                        data=result['word_bytes'],
                        file_name=f"Report_{source}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary"
                    )
                
                if debug and result.get('debug_mode'):
                    # Show debug components if available, else raw json
                    try:
                        from ui.debug_components import show_debug_results
                        show_debug_results(result, None)
                    except ImportError:
                        st.json(result.get('violations', []))
                else:
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
                        if res.get('word_bytes'):
                            st.download_button(
                                f"Download {fname}", 
                                res['word_bytes'], 
                                f"{fname}.docx",
                                key=f"dl_{fname}"
                            )
                        st.markdown(res['report'])
                    else:
                        st.error(res.get('error'))
