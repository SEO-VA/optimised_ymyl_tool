#!/usr/bin/env python3
import streamlit as st
from utils.feature_registry import FeatureRegistry
from core.processor import processor
from core.state import state_manager
from ui.content_preview import render_content_preview


class UserLayout:
    def render(self, selected_feature: str):
        try:
            feature_handler = FeatureRegistry.get_handler(selected_feature)
        except ValueError as e:
            st.error(f"❌ {str(e)}")
            return

        analysis_key = f"user_analysis_{selected_feature}"
        extract_key = f"user_extracted_{selected_feature}"
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

        # Determine current step
        has_extraction = bool(st.session_state.get(extract_key))
        has_result = bool(st.session_state.get(f'{analysis_key}_complete'))

        if has_result:
            self._show_single_file_results(analysis_key, extract_key)
            return

        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            if not has_extraction:
                btn_text = "🔍 Extract Content" if not is_multi else "🔍 Extract All Files"
                if st.button(btn_text, type="primary", use_container_width=True,
                             disabled=not input_data.get('is_valid', False) or is_processing):
                    state_manager.is_processing = True
                    st.rerun()
            else:
                col_analyze, col_reset = st.columns([3, 1])
                with col_analyze:
                    if st.button("🚀 Run Analysis", type="primary", use_container_width=True,
                                 disabled=is_processing):
                        state_manager.is_processing = True
                        st.session_state[f'{analysis_key}_run'] = True
                        st.rerun()
                with col_reset:
                    if st.button("↩️ Re-extract", use_container_width=True):
                        for k in [extract_key, f"user_source_{selected_feature}"]:
                            st.session_state.pop(k, None)
                        st.rerun()

        # Step 1: Extract
        if state_manager.is_processing and not has_extraction and not st.session_state.get(f'{analysis_key}_run'):
            self._do_extract(feature_handler, input_data, selected_feature)
            return

        # Step 2: Run analysis
        if state_manager.is_processing and st.session_state.get(f'{analysis_key}_run'):
            content = st.session_state.get(extract_key)
            source = st.session_state.get(f"user_source_{selected_feature}", "content")
            self._run_analysis(content, source, analysis_key, selected_feature, topic_description)
            return

        # Show content preview after extraction
        if has_extraction:
            with st.expander("📋 Content Preview — verify before analysis", expanded=True):
                render_content_preview(st.session_state[extract_key])

    def _do_extract(self, feature_handler, input_data, feature_key):
        extract_key = f"user_extracted_{feature_key}"
        try:
            with st.status("🔍 Extracting content...", expanded=True) as status:
                st.write("📄 Parsing page structure...")
                success, content, err = feature_handler.extract_content(input_data)
                if not success:
                    raise ValueError(err)
                st.session_state[extract_key] = content
                st.session_state[f"user_source_{feature_key}"] = feature_handler.get_source_description(input_data)
                status.update(label="✅ Extraction complete — review the preview below", state="complete", expanded=False)
                state_manager.is_processing = False
                st.rerun()
        except Exception as e:
            st.error(f"❌ Extraction failed: {str(e)}")
            state_manager.is_processing = False

    def _run_analysis(self, content, source, analysis_key, feature_key, topic_description):
        try:
            with st.status("🚀 Running 3-Stage AI Analysis...", expanded=True) as status:
                st.write("🤖 Running 3 detection lenses in parallel...")
                result = processor.process_single_file(
                    content=content,
                    source_description=source,
                    topic_description=topic_description
                )

                if not result.get('success'):
                    raise ValueError(result.get('error'))

                st.write("📝 Generating Word Report...")
                status.update(label="✅ Analysis Complete!", state="complete", expanded=False)

                st.session_state[f'{analysis_key}_complete'] = True
                st.session_state[f'{analysis_key}_report'] = result['report']
                st.session_state[f'{analysis_key}_word_bytes'] = result.get('word_bytes')
                st.session_state.pop(f'{analysis_key}_run', None)
                state_manager.is_processing = False
                st.rerun()
        except Exception as e:
            st.error(f"❌ {str(e)}")
            st.session_state.pop(f'{analysis_key}_run', None)
            state_manager.is_processing = False

    def _run_multi_file(self, feature_handler, input_data, topic_description):
        pass

    def _show_single_file_results(self, key, extract_key):
        st.success("✅ Analysis Ready")
        if st.session_state.get(f'{key}_word_bytes'):
            st.download_button("📄 Download Word Report", st.session_state[f'{key}_word_bytes'], "report.docx")

        tab_report, tab_preview = st.tabs(["📄 Audit Report", "📋 Extracted Content"])
        with tab_report:
            st.markdown(st.session_state.get(f'{key}_report', ''))
        with tab_preview:
            if st.session_state.get(extract_key):
                render_content_preview(st.session_state[extract_key])
            else:
                st.info("Extracted content not available.")

        if st.button("🔄 Start New Analysis"):
            prefix = key.replace('user_analysis_', 'user_')
            keys_to_del = [k for k in st.session_state.keys()
                           if k.startswith(key) or k == extract_key or k.startswith(prefix)]
            for k in keys_to_del:
                del st.session_state[k]
            st.rerun()

    def _get_multi_file_results(self):
        return None

    def _show_multi_file_results(self, results):
        pass
