#!/usr/bin/env python3
"""
Admin Layout - Standard Edition
Restored to stable state (No Translation Toggle).
"""

import streamlit as st
from utils.feature_registry import FeatureRegistry
from core.processor import processor
from utils.helpers import trigger_completion_notification
from ui.content_preview import render_content_preview
from ui.content_selection import filter_content_json
import json
from dataclasses import is_dataclass, asdict

class AdminLayout:
    _SELECTION_KEY = "admin_section_selection"
    
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
        with col2:
            if st.button("🔄 Reset All", use_container_width=True):
                self._smart_reset()

    def _smart_reset(self):
        keys_to_keep = ['authenticated', 'username', 'global_topic_description']
        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]
        st.rerun()

    def _render_step1(self, handler):
        st.subheader("Step 1: Extraction")
        input_data = handler.get_input_interface()
        
        st.markdown("---")
        current_topic = st.session_state.get('global_topic_description', 'Online casino affiliate site')
        topic_description = st.text_input(
            "Content topic",
            value=current_topic,
            help="Describe the type of content being analyzed. Injected into all audit prompts."
        )
        st.session_state['global_topic_description'] = topic_description
        input_data['topic_description'] = topic_description
        
        is_multi = handler.is_multi_file_input(input_data) if hasattr(handler, 'is_multi_file_input') else False
        st.markdown("---")
        
        if st.button("Extract Content", type="primary"):
            is_valid, validation_message = handler.validate_input(input_data)
            if not is_valid:
                st.warning(f"⚠️ {validation_message}")
                return

            with st.spinner("Extracting..."):
                success, content, err = handler.extract_content(input_data)
                if success:
                    if is_multi:
                        st.session_state['admin_multi_extracted'] = content
                    else:
                        st.session_state['extracted_content'] = content
                        st.session_state['source_info'] = handler.get_source_description(input_data)
                        st.session_state.pop(self._SELECTION_KEY, None)
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

        debug = st.checkbox("Debug Mode", value=True)
        topic_description = st.session_state.get('global_topic_description', 'Online casino affiliate site')

        if st.button("🚀 Run Analysis", type="primary", use_container_width=True):
            if is_multi:
                self._run_multi(st.session_state['admin_multi_extracted'], debug, topic_description)
            else:
                filtered = filter_content_json(
                    st.session_state['extracted_content'],
                    st.session_state.get(self._SELECTION_KEY),
                )
                if filtered is None:
                    st.warning("⚠️ No sections selected. Please select at least one section to analyze.")
                    return
                self._run_single(filtered, st.session_state['source_info'], debug, topic_description)

    def _render_single_preview(self):
        content = st.session_state.get('extracted_content', '')
        tab_visual, tab_json = st.tabs(["📋 Visual Preview", "🔧 Raw JSON"])
        with tab_visual:
            render_content_preview(content, selection_key=self._SELECTION_KEY)
        with tab_json:
            st.code(content, language='json')

    def _render_multi_preview(self):
        content_json = st.session_state.get('admin_multi_extracted', '{}')
        try:
            files = json.loads(content_json).get('files', {})
            preview_file = st.selectbox("Inspect file:", list(files.keys()))
            if preview_file:
                with st.expander(f"View: {preview_file}"):
                    st.code(files[preview_file], language='json')
        except: pass

    def _sanitize_for_display(self, result_dict):
        return self._to_display_safe(result_dict)

    def _to_display_safe(self, value):
        if is_dataclass(value):
            return self._to_display_safe(asdict(value))
        if isinstance(value, dict):
            clean = {}
            for key, item in value.items():
                if key == 'word_bytes' and item:
                    clean[key] = "<Word Document>"
                else:
                    clean[key] = self._to_display_safe(item)
            return clean
        if isinstance(value, list):
            return [self._to_display_safe(item) for item in value]
        return value

    def _run_single(self, content, source, debug, topic_description):
        with st.status("Analyzing... (3-stage pipeline)") as status:
            result = processor.process_single_file(content, source, topic_description, debug)
            
            if result['success']:
                status.update(label="Done", state="complete")
                trigger_completion_notification()
                
                if result.get('word_bytes'):
                    st.download_button("📄 Download Report", result['word_bytes'], f"Report_{source}.docx", type="primary", use_container_width=True)
                
                if debug and result.get('debug_info'):
                    st.divider()
                    st.subheader("🔍 Pipeline Debug Inspector")
                    debug_info = result.get("debug_info", {})

                    with st.expander(f"Stage 1: Detection ({len(debug_info.get('detection', []))} lenses)", expanded=False):
                        st.json(self._sanitize_for_display(debug_info.get("detection", [])))

                    with st.expander("Stage 2: Verification", expanded=False):
                        st.json(self._sanitize_for_display(debug_info.get("verification", {})))

                    with st.expander("Stage 3: Finalization", expanded=False):
                        st.json(self._sanitize_for_display(debug_info.get("finalization", {})))

                    with st.expander("Summary", expanded=True):
                        st.json(self._sanitize_for_display({
                            "processing_time": result.get("processing_time"),
                            "total_candidates": result.get("total_violations_found"),
                            "unique_violations": result.get("unique_violations"),
                        }))
            else:
                st.error(result.get('error'))

    def _run_multi(self, content_json, debug, topic_description):
        files = json.loads(content_json).get('files', {})
        with st.status(f"Analyzing {len(files)} files...") as status:
            results = processor.process_multi_file(files, topic_description, debug)
            status.update(label="Done", state="complete")
            trigger_completion_notification()
            
            for fname, res in results.items():
                with st.expander(f"{fname} ({'Success' if res['success'] else 'Failed'})"):
                    if res['success']:
                        if res.get('word_bytes'):
                            st.download_button(f"Download {fname}", res['word_bytes'], f"{fname}.docx", key=f"dl_{fname}")
                    else:
                        st.error(res.get('error'))
