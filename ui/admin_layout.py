#!/usr/bin/env python3
"""
Admin Layout
Advanced interface with Debug Mode.
Updated: Triggers Notification on Success.
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
                content_len = 0
                if 'extracted_content' in st.session_state:
                    content_len = len(st.session_state['extracted_content'])
                st.write(f"**Content Size:** {content_len} chars")

        col1, col2 = st.columns([3, 1])
        with col1:
            if self.current_step == 1:
                self._render_step1(feature_handler)
            else:
                self._render_step2(feature_handler)
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
        input_data['casino_mode'] = st.session_state.get('global_casino_mode', False)
        is_multi = handler.is_multi_file_input(input_data) if hasattr(handler, 'is_multi_file_input') else False
        
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
        audit_count = 1 if test_mode else 5
        
        casino_mode = st.session_state.get('global_casino_mode', False)
        
        if st.button(f"🚀 Run Analysis ({audit_count} Audits)", type="primary", use_container_width=True):
            if is_multi:
                self._run_multi(st.session_state['admin_multi_extracted'], debug, audit_count, casino_mode)
            else:
                self._run_single(st.session_state['extracted_content'], st.session_state['source_info'], debug, audit_count, casino_mode)

    def _render_single_preview(self):
        content = st.session_state.get('extracted_content', '')
        st.info(f"✅ Content Extracted: {len(content)} characters")
        with st.expander("👁️ View Extracted JSON", expanded=True):
            st.code(content, language='json')

    def _render_multi_preview(self):
        content_json = st.session_state.get('admin_multi_extracted', '{}')
        try:
            files = json.loads(content_json).get('files', {})
            st.info(f"✅ Extracted {len(files)} files")
            preview_file = st.selectbox("Inspect file:", list(files.keys()))
            if preview_file:
                with st.expander(f"View: {preview_file}"):
                    st.code(files[preview_file], language='json')
        except:
            st.error("Invalid multi-file JSON")

    def _run_single(self, content, source, debug, count, casino_mode):
        with st.status(f"Analyzing... ({count} audits)") as status:
            result = processor.process_single_file(
                content=content, 
                source_description=source, 
                casino_mode=casino_mode, 
                debug_mode=debug, 
                audit_count=count
            )
            
            if result['success']:
                status.update(label="Done", state="complete")
                trigger_completion_notification() # <-- NOTIFICATION
                
                if result.get('word_bytes'):
                    st.download_button(
                        label="📄 Download Word Report", 
                        data=result['word_bytes'],
                        file_name=f"Report_{source}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary", 
                        use_container_width=True
                    )
                
                if debug and result.get('debug_mode'):
                    try:
                        from ui.debug_components import show_debug_results
                        show_debug_results(result, None)
                    except ImportError:
                        st.json(result.get('violations', []))
                else:
                    st.markdown(result['report'])
            else:
                st.error(result.get('error'))

    def _run_multi(self, content_json, debug, count, casino_mode):
        files = json.loads(content_json).get('files', {})
        with st.status(f"Analyzing {len(files)} files...") as status:
            results = processor.process_multi_file(files, casino_mode, debug, count)
            status.update(label="Done", state="complete")
            
            trigger_completion_notification() # <-- NOTIFICATION
            
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
