#!/usr/bin/env python3
"""
Admin Layout
Updated:
1. Logs Persist after download (Display logic separated from processing logic).
2. All options moved to Main Interface.
3. Granular Status Feedback.
"""

import streamlit as st
from utils.feature_registry import FeatureRegistry
from core.processor import processor
from utils.helpers import trigger_completion_notification
import json

class AdminLayout:
    
    def __init__(self):
        # Determine current step based on data presence
        self.current_step = 2 if st.session_state.get('extracted_content') or st.session_state.get('admin_multi_extracted') else 1
    
    def render(self, selected_feature: str):
        try:
            feature_handler = FeatureRegistry.get_handler(selected_feature)
        except ValueError as e:
            st.error(f"❌ {str(e)}")
            return
        
        # --- PERSISTENT INSPECTOR (Left Column) ---
        # We use col1 for controls/status and col2 for results
        
        if self.current_step == 1:
            self._render_step1(feature_handler)
        else:
            self._render_step2(feature_handler)

    def _smart_reset(self):
        keys_to_keep = ['authenticated', 'username']
        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]
        st.rerun()

    def _render_step1(self, handler):
        st.subheader("Step 1: Extraction")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            input_data = handler.get_input_interface()
            
            # Casino Mode is now a Global Setting for extraction
            casino_mode = st.checkbox("🎰 Casino Mode (Surgical Extraction)", value=False)
            input_data['casino_mode'] = casino_mode
            
        with col2:
            st.write("### Actions")
            if st.button("📄 Extract Content", type="primary", use_container_width=True, disabled=not input_data.get('is_valid')):
                with st.status("Extracting...", expanded=True):
                    st.write("Parsing HTML structure...")
                    success, content, err = handler.extract_content(input_data)
                    
                    if success:
                        st.write("✅ Extraction successful!")
                        is_multi = handler.is_multi_file_input(input_data) if hasattr(handler, 'is_multi_file_input') else False
                        
                        if is_multi:
                            st.session_state['admin_multi_extracted'] = content
                        else:
                            st.session_state['extracted_content'] = content
                            st.session_state['source_info'] = handler.get_source_description(input_data)
                        st.session_state['global_casino_mode'] = casino_mode
                        st.rerun()
                    else:
                        st.error(f"Extraction Failed: {err}")

    def _render_step2(self, handler):
        # --- CONTROLS SECTION ---
        st.subheader("Step 2: AI Analysis")
        
        col_opts, col_actions = st.columns([2, 1])
        
        with col_opts:
            # MAIN INTERFACE OPTIONS
            c1, c2, c3 = st.columns(3)
            debug = c1.checkbox("🐛 Debug Mode", value=True, help="Show raw JSON and Inspector")
            test_mode = c2.checkbox("🧪 Test Mode (1 Audit)", value=False, help="Fast check, skips deduplication")
            # Read-only view of mode selected in Step 1
            casino_mode = st.session_state.get('global_casino_mode', False)
            c3.info(f"Mode: {'🎰 Casino' if casino_mode else '🌐 Generic'}")
            
            audit_count = 1 if test_mode else 5

        with col_actions:
            if st.button("🗑️ Discard & Restart", use_container_width=True):
                self._smart_reset()
            
            if st.button(f"🚀 Run Analysis ({audit_count})", type="primary", use_container_width=True):
                self._trigger_analysis(debug, audit_count, casino_mode)

        st.divider()

        # --- RESULTS SECTION (Persistent) ---
        # This runs on every refresh. If results exist, they show up.
        if 'admin_last_result' in st.session_state:
            self._display_results(st.session_state['admin_last_result'], debug)
        
        # --- PREVIEW SECTION (Always visible) ---
        elif st.session_state.get('extracted_content'):
            self._render_single_preview()

    def _trigger_analysis(self, debug, count, casino_mode):
        """Runs the analysis and SAVES result to session_state"""
        is_multi = 'admin_multi_extracted' in st.session_state
        
        if is_multi:
            self._run_multi(st.session_state['admin_multi_extracted'], debug, count, casino_mode)
        else:
            content = st.session_state['extracted_content']
            source = st.session_state['source_info']
            
            with st.status(f"🚀 Analyzing {source}...", expanded=True) as status:
                st.write("📡 Initializing Agents...")
                result = processor.process_single_file(content, source, casino_mode, debug, count)
                
                if result['success']:
                    st.write("✅ Analysis Complete")
                    st.write("💾 Saving Results...")
                    # SAVE RESULT TO STATE SO IT SURVIVES RERUNS
                    st.session_state['admin_last_result'] = result
                    status.update(label="Done!", state="complete", expanded=False)
                    st.rerun()
                else:
                    st.error(result.get('error'))

    def _display_results(self, result, debug):
        """Renders the results from the stored state"""
        st.success("✅ Analysis Results Ready")
        
        # Download Button (This triggers rerun, but data is safe in session_state['admin_last_result'])
        if result.get('word_bytes'):
            st.download_button(
                label="📄 Download Word Report", 
                data=result['word_bytes'],
                file_name="admin_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True
            )

        # INSPECTOR
        if debug and result.get('debug_info'):
            st.divider()
            st.subheader("🔍 AI Raw Output Inspector")
            d_info = result['debug_info']
            
            tab0, tab1, tab2, tab3 = st.tabs(["0️⃣ Input to Deduplicator", "1️⃣ Deduplicator Output", "2️⃣ Audits", "3️⃣ Final JSON"])
            
            with tab0:
                st.caption("Exact JSON sent to Agent 2 (Filter):")
                st.code(d_info.get('deduplicator_input', 'N/A'), language='json')

            with tab1:
                st.caption("Raw Text from Agent 2:")
                st.text_area("Raw Deduplicator", d_info.get('deduplicator_raw', 'N/A'), height=400)
            
            with tab2:
                audits = d_info.get('audits', [])
                for a in audits:
                    with st.expander(f"Audit #{a.get('audit_number')}"):
                        st.code(a.get('raw_response'), language='json')

            with tab3:
                st.caption("Final Cleaned JSON Structure:")
                # Sanitize to hide binary data
                clean_res = result.copy()
                if 'word_bytes' in clean_res: clean_res['word_bytes'] = "<Binary Data Hidden>"
                st.json(clean_res.get('violations', []))

        elif not debug:
            st.markdown(result['report'])

    def _render_single_preview(self):
        content = st.session_state.get('extracted_content', '')
        st.info(f"Ready to analyze. Extracted {len(content)} chars.")
        with st.expander("👁️ View Extracted Data Payload"):
            st.code(content, language='json')

    def _run_multi(self, content_json, debug, count, casino_mode):
        # Similar update for multi-file: Save results to session state
        pass
