#!/usr/bin/env python3
"""
Admin Layout - Standard Edition
Restored to stable state (No Translation Toggle).
"""

import streamlit as st
from utils.feature_registry import FeatureRegistry
from core.processor import processor
from core.google_oauth import (
    clear_analysis_snapshot,
    get_credentials,
    prepare_auth_url,
)
from utils.helpers import trigger_completion_notification
from ui.content_preview import render_content_preview
from ui.content_selection import filter_content_json
from core.auth import get_current_user
from dataclasses import is_dataclass, asdict


class AdminLayout:
    _SELECTION_KEY = "admin_section_selection"
    
    def __init__(self):
        self.current_step = 2 if st.session_state.get('extracted_content') or st.session_state.get('admin_multi_extracted') else 1
    
    def render(self, selected_feature: str):
        snapshot_context = f"admin:{selected_feature}"
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
                self._render_step2(feature_handler, snapshot_context)
        with col2:
            if st.button("🔄 Reset All", use_container_width=True):
                self._smart_reset(snapshot_context)

    def _smart_reset(self, snapshot_context: str = ""):
        clear_analysis_snapshot(get_current_user(), snapshot_context)
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

    def _render_step2(self, handler, snapshot_context: str):
        col_head, col_btn = st.columns([3, 1])
        with col_head:
            st.subheader("Step 2: Analysis")
        with col_btn:
            if st.button("🗑️ Discard & Restart", type="secondary", use_container_width=True):
                self._smart_reset(snapshot_context)

        if st.session_state.get('admin_analysis_complete'):
            self._show_admin_results(snapshot_context)
            return

        is_multi = 'admin_multi_extracted' in st.session_state
        if is_multi:
            self._render_multi_preview()
        else:
            self._render_single_preview()

        st.divider()

        col_debug, col_mock = st.columns(2)
        with col_debug:
            debug = st.checkbox("Debug Mode", value=True)
        with col_mock:
            mock_mode = st.checkbox("🧪 Mock Mode (skip API calls)", value=False)
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
                self._run_single(filtered, st.session_state['source_info'], debug, topic_description, mock_mode)

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

    def _run_single(self, content, source, debug, topic_description, mock_mode=False):
        label = "Running mock analysis..." if mock_mode else "Analyzing... (3-stage pipeline)"
        with st.status(label) as status:
            result = processor.process_single_file(content, source, topic_description, debug, mock_mode)

            if result['success']:
                status.update(label="Done", state="complete")
                trigger_completion_notification()
                st.session_state['admin_analysis_complete'] = True
                st.session_state['admin_analysis_word_bytes'] = result.get('word_bytes')
                st.session_state['admin_analysis_violations'] = result.get('violations', [])
                st.session_state['admin_analysis_report'] = result.get('report', '')
                st.session_state['admin_analysis_source'] = source
                st.session_state['admin_analysis_content'] = content
                st.session_state['admin_analysis_debug_mode'] = debug
                st.session_state['admin_analysis_debug_info'] = result.get('debug_info')
                st.session_state['admin_analysis_processing_time'] = result.get('processing_time')
                st.session_state['admin_analysis_total_violations'] = result.get('total_violations_found')
                st.session_state['admin_analysis_unique_violations'] = result.get('unique_violations')
                st.rerun()
            else:
                st.error(result.get('error'))

    def _show_admin_results(self, snapshot_context: str = ""):
        source = st.session_state.get('admin_analysis_source', 'content')
        user_email = get_current_user()
        snapshot_keys = [
            "main_analysis_type",
            "test_warning_dismissed",
            "extracted_content",
            "source_info",
            self._SELECTION_KEY,
            "admin_analysis_complete",
            "admin_analysis_word_bytes",
            "admin_analysis_violations",
            "admin_analysis_report",
            "admin_analysis_source",
            "admin_analysis_content",
            "admin_analysis_debug_mode",
            "admin_analysis_debug_info",
            "admin_analysis_processing_time",
            "admin_analysis_total_violations",
            "admin_analysis_unique_violations",
            "admin_analysis_gdoc_url",
        ]

        col_word, col_gdoc = st.columns([1, 1])
        with col_word:
            word_bytes = st.session_state.get('admin_analysis_word_bytes')
            if word_bytes:
                st.download_button("📄 Download Report", word_bytes, f"Report_{source}.docx", type="primary", use_container_width=True)

        with col_gdoc:
            gdoc_url = st.session_state.get('admin_analysis_gdoc_url')
            if gdoc_url:
                st.link_button("📝 Open Google Doc", gdoc_url, use_container_width=True)
            elif not st.secrets.get("google_docs"):
                st.error("❌ Google Docs not configured. Add `[google_docs]` to `.streamlit/secrets.toml`")
            elif not get_credentials(user_email):
                try:
                    auth_url = prepare_auth_url(user_email, snapshot_context, snapshot_keys)
                except Exception as e:
                    st.error(f"❌ Google authorization is not available: {str(e)}")
                else:
                    st.link_button(
                        "🔑 Authorize Google Drive",
                        auth_url,
                        use_container_width=True,
                        type="primary",
                    )
            else:
                if st.button("📝 Create Google Doc with Comments", use_container_width=True):
                    violations = st.session_state.get('admin_analysis_violations', [])
                    content = st.session_state.get('admin_analysis_content', '{}')
                    report = st.session_state.get('admin_analysis_report', '')
                    title = f"YMYL Audit - {source}"
                    with st.spinner("Creating Google Doc..."):
                        try:
                            url = processor.generate_google_doc(content, violations, user_email, title, report_markdown=report)
                            st.session_state['admin_analysis_gdoc_url'] = url
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Failed to create Google Doc: {str(e)}")

        report_md = st.session_state.get('admin_analysis_report', '')
        tab_report, tab_preview = st.tabs(["📄 Audit Report", "📋 Extracted Content"])
        with tab_report:
            if report_md:
                st.markdown(report_md)
            else:
                st.warning("⚠️ No report in session state")
        with tab_preview:
            content = st.session_state.get('admin_analysis_content', '')
            if content:
                st.code(content, language='json')

        debug = st.session_state.get('admin_analysis_debug_mode', False)
        debug_info = st.session_state.get('admin_analysis_debug_info')
        if debug and debug_info:
            st.divider()
            st.subheader("🔍 Pipeline Debug Inspector")

            with st.expander(f"Stage 1: Detection ({len(debug_info.get('detection', []))} lenses)", expanded=False):
                st.json(self._sanitize_for_display(debug_info.get("detection", [])))

            with st.expander("Stage 2: Verification", expanded=False):
                st.json(self._sanitize_for_display(debug_info.get("verification", {})))

            with st.expander("Stage 3: Finalization", expanded=False):
                st.json(self._sanitize_for_display(debug_info.get("finalization", {})))

            with st.expander("Summary", expanded=True):
                st.json(self._sanitize_for_display({
                    "processing_time": st.session_state.get('admin_analysis_processing_time'),
                    "total_candidates": st.session_state.get('admin_analysis_total_violations'),
                    "unique_violations": st.session_state.get('admin_analysis_unique_violations'),
                }))

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
