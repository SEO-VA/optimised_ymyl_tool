#!/usr/bin/env python3
"""
User Layout
Standard interface for running 5-Audit analysis.
Delegates all heavy lifting to core.processor.
"""

import streamlit as st
from typing import Dict, Any
from utils.feature_registry import FeatureRegistry
from core.processor import processor
from core.state import state_manager

class UserLayout:
    """User layout with simplified logic using AnalysisProcessor"""
    
    def render(self, selected_feature: str, casino_mode: bool = False):
        try:
            feature_handler = FeatureRegistry.get_handler(selected_feature)
        except ValueError as e:
            st.error(f"❌ {str(e)}")
            return
        
        analysis_key = f"user_analysis_{selected_feature}"
        
        # Check for existing results
        if st.session_state.get(f'{analysis_key}_complete'):
            self._show_single_file_results(analysis_key)
            return
        
        # Check for multi-file results
        multi_results = self._get_multi_file_results()
        if multi_results:
            self._show_multi_file_results(multi_results)
            return
        
        # Render Input
        self._render_analysis_interface(feature_handler, analysis_key, casino_mode)

    def _render_analysis_interface(self, feature_handler, analysis_key: str, casino_mode: bool):
        is_processing = state_manager.is_processing
        input_data = feature_handler.get_input_interface(disabled=is_processing)
        input_data['casino_mode'] = casino_mode
        
        is_multi = feature_handler.is_multi_file_input(input_data) if hasattr(feature_handler, 'is_multi_file_input') else False
        
        if is_multi and hasattr(feature_handler, 'get_file_list'):
            files = feature_handler.get_file_list(input_data)
            if files: st.info(f"📁 **{len(files)} files selected**")

        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            btn_text = "🚀 Analyze All Files" if is_multi else "🚀 Analyze Content"
            if st.button(btn_text, type="primary", use_container_width=True, 
                        disabled=not input_data.get('is_valid', False) or is_processing):
                state_manager.is_processing = True
                st.rerun()

        # Execute if processing flag is set
        if state_manager.is_processing and not state_manager.stop_signal:
            if is_multi:
                self._run_multi_file(feature_handler, input_data)
            else:
                self._run_single_file(feature_handler, input_data, analysis_key)

    def _run_single_file(self, feature_handler, input_data, analysis_key):
        try:
            with st.status("Running multi-audit analysis...") as status:
                success, content, err = feature_handler.extract_content(input_data)
                if not success: raise ValueError(err)
                
                status.update(label="Content extracted, running 5 parallel AI audits...", state="running")
                
                # Call Processor
                result = processor.process_single_file(
                    content=content,
                    source_description=feature_handler.get_source_description(input_data),
                    casino_mode=input_data.get('casino_mode', False)
                )
                
                if not result.get('success'): raise ValueError(result.get('error'))

                status.update(label="✅ Analysis complete!", state="complete")
                
                # Store
                st.session_state[f'{analysis_key}_complete'] = True
                st.session_state[f'{analysis_key}_report'] = result['report']
                st.session_state[f'{analysis_key}_word_bytes'] = result.get('word_bytes')
                state_manager.is_processing = False
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ {str(e)}")
            state_manager.is_processing = False

    def _run_multi_file(self, feature_handler, input_data):
        try:
            import json
            with st.status("Processing multiple files...") as status:
                success, content, err = feature_handler.extract_content(input_data)
                if not success: raise ValueError(err)
                
                files_data = json.loads(content).get('files', {})
                status.update(label=f"Starting parallel analysis of {len(files_data)} files...", state="running")

                # Callback for UI updates
                def update_ui(fname, state):
                    st.session_state[f'multi_{fname}_status'] = state
                
                for fname in files_data: update_ui(fname, 'processing')

                # Call Processor
                results = processor.process_multi_file(
                    files_data=files_data,
                    casino_mode=input_data.get('casino_mode', False),
                    status_callback=update_ui
                )
                
                status.update(label="✅ All files processed!", state="complete")
                
                # Store results
                for fname, res in results.items():
                    if res.get('success'):
                        st.session_state[f'multi_{fname}_report'] = res['report']
                        st.session_state[f'multi_{fname}_word_bytes'] = res.get('word_bytes')
                    else:
                        st.session_state[f'multi_{fname}_error'] = res.get('error')

                state_manager.is_processing = False
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ {str(e)}")
            state_manager.is_processing = False

    def _show_single_file_results(self, key):
        st.success("✅ Analysis Complete")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.session_state.get(f'{key}_word_bytes'):
                st.download_button("📄 Download Report", 
                                 data=st.session_state[f'{key}_word_bytes'],
                                 file_name="ymyl_report.docx",
                                 mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with col2:
            if st.button("🔄 New Analysis"):
                keys = [k for k in st.session_state.keys() if k.startswith(key)]
                for k in keys: del st.session_state[k]
                st.rerun()
                
        st.markdown(st.session_state.get(f'{key}_report', ''))

    def _get_multi_file_results(self):
        results = {}
        for k in st.session_state:
            if k.startswith('multi_') and k.endswith('_status'):
                fname = k[6:-7]
                results[fname] = {'status': st.session_state[k]}
        return results if results else None

    def _show_multi_file_results(self, results):
        st.success(f"✅ Processed {len(results)} files")
        if st.button("🔄 New Analysis"):
            keys = [k for k in st.session_state.keys() if k.startswith('multi_')]
            for k in keys: del st.session_state[k]
            st.rerun()
        
        for fname, data in results.items():
            status = data['status']
            if status == 'complete':
                st.success(f"{fname}: Complete")
                bytes_data = st.session_state.get(f'multi_{fname}_word_bytes')
                if bytes_data:
                    st.download_button(f"Download {fname}", bytes_data, file_name=f"{fname}.docx", key=f"dl_{fname}")
            elif status == 'failed':
                err = st.session_state.get(f'multi_{fname}_error', 'Unknown error')
                st.error(f"{fname}: Failed - {err}")
