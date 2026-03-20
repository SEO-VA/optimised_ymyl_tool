#!/usr/bin/env python3
import streamlit as st
from utils.feature_registry import FeatureRegistry
from core.processor import processor
from core.state import state_manager

class UserLayout:
    def render(self, selected_feature: str):
        try:
            feature_handler = FeatureRegistry.get_handler(selected_feature)
        except ValueError as e:
            st.error(f"❌ {str(e)}")
            return
        
        analysis_key = f"user_analysis_{selected_feature}"
        is_processing = state_manager.is_processing
        
        col_input, col_opts = st.columns([3, 1])
        with col_input:
            input_data = feature_handler.get_input_interface(disabled=is_processing)
        
        with col_opts:
            st.markdown("### ⚙️ Options")
            topic_description = st.text_input(
                "Content topic",
                value="Online casino affiliate site",
                help="Describe the type of content being analyzed. Used to adapt the audit prompts.",
                disabled=is_processing
            )
            input_data['topic_description'] = topic_description

        st.markdown("---")
        is_multi = feature_handler.is_multi_file_input(input_data) if hasattr(feature_handler, 'is_multi_file_input') else False
        
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            btn_text = "🚀 Analyze All Files" if is_multi else "🚀 Analyze Content"
            if st.button(btn_text, type="primary", use_container_width=True, 
                        disabled=not input_data.get('is_valid', False) or is_processing):
                state_manager.is_processing = True
                if f'{analysis_key}_complete' in st.session_state:
                    del st.session_state[f'{analysis_key}_complete']
                st.rerun()

        if state_manager.is_processing and not state_manager.stop_signal:
            if is_multi:
                self._run_multi_file(feature_handler, input_data, topic_description)
            else:
                self._run_single_file(feature_handler, input_data, analysis_key, topic_description)

        if st.session_state.get(f'{analysis_key}_complete'):
            self._show_single_file_results(analysis_key)

    def _run_single_file(self, feature_handler, input_data, analysis_key, topic_description):
        try:
            with st.status("🚀 Starting Analysis...", expanded=True) as status:
                st.write("📄 Extracting content...")
                success, content, err = feature_handler.extract_content(input_data)
                if not success: raise ValueError(err)

                st.write("🤖 Running 3-Stage AI Analysis...")
                result = processor.process_single_file(
                    content=content,
                    source_description=feature_handler.get_source_description(input_data),
                    topic_description=topic_description
                )
                
                if not result.get('success'): raise ValueError(result.get('error'))

                st.write("📝 Generating Word Report...")
                status.update(label="✅ Analysis Complete!", state="complete", expanded=False)
                
                st.session_state[f'{analysis_key}_complete'] = True
                st.session_state[f'{analysis_key}_report'] = result['report']
                st.session_state[f'{analysis_key}_word_bytes'] = result.get('word_bytes')
                state_manager.is_processing = False
                st.rerun()
        except Exception as e:
            st.error(f"❌ {str(e)}")
            state_manager.is_processing = False

    def _run_multi_file(self, feature_handler, input_data, topic_description): pass
    def _show_single_file_results(self, key):
        st.success("✅ Analysis Ready")
        if st.session_state.get(f'{key}_word_bytes'):
            st.download_button("📄 Download Word Report", st.session_state[f'{key}_word_bytes'], "report.docx")
        with st.expander("👁️ View Report Preview", expanded=True):
            st.markdown(st.session_state.get(f'{key}_report', ''))
        if st.button("🔄 Start New Analysis"):
            keys = [k for k in st.session_state.keys() if k.startswith(key)]
            for k in keys: del st.session_state[k]
            st.rerun()
    def _get_multi_file_results(self): return None
    def _show_multi_file_results(self, results): pass
