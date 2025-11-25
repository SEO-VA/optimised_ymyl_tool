#!/usr/bin/env python3
"""
User Layout
Updated: Added 'Translate to English' toggle.
"""

import streamlit as st
from typing import Dict, Any
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
        
        # --- SECTION 1: INPUT & CONTROLS ---
        is_processing = state_manager.is_processing
        
        col_input, col_opts = st.columns([3, 1])
        
        with col_input:
            input_data = feature_handler.get_input_interface(disabled=is_processing)
        
        with col_opts:
            st.markdown("### ⚙️ Options")
            casino_mode = st.checkbox(
                "🎰 Casino Mode", 
                value=False,
                help="Enables specialized 'Surgical Extraction' for casino reviews.",
                disabled=is_processing
            )
            
            # --- NEW TOGGLE ---
            translate_mode = st.checkbox(
                "🌐 Translate to English",
                value=True, 
                help="If unchecked, the report will remain in the original language (e.g., Finnish).",
                disabled=is_processing
            )
            
            # Save to input data
            input_data['casino_mode'] = casino_mode
            input_data['translate_mode'] = translate_mode

        # --- SECTION 2: ACTION BUTTON ---
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

        # --- SECTION 3: PROCESSING LOGIC ---
        if state_manager.is_processing and not state_manager.stop_signal:
            if is_multi:
                self._run_multi_file(feature_handler, input_data, casino_mode, translate_mode)
            else:
                self._run_single_file(feature_handler, input_data, analysis_key, casino_mode, translate_mode)

        # --- SECTION 4: RESULT DISPLAY ---
        if st.session_state.get(f'{analysis_key}_complete'):
            self._show_single_file_results(analysis_key)
        
        multi_results = self._get_multi_file_results()
        if multi_results:
            self._show_multi_file_results(multi_results)

    def _run_single_file(self, feature_handler, input_data, analysis_key, casino_mode, translate_mode):
        try:
            with st.status("🚀 Starting Analysis...", expanded=True) as status:
                
                st.write("📄 Extracting content...")
                success, content, err = feature_handler.extract_content(input_data)
                if not success: raise ValueError(err)
                
                st.write("🤖 Running 5 Parallel AI Audits (This takes ~30-60s)...")
                
                # Pass translate_mode to processor
                result = processor.process_single_file(
                    content=content,
                    source_description=feature_handler.get_source_description(input_data),
                    casino_mode=casino_mode,
                    translate_mode=translate_mode
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

    def _run_multi_file(self, feature_handler, input_data, casino_mode, translate_mode):
        # Placeholder for multi-file logic implementation matching single file
        pass 

    def _show_single_file_results(self, key):
        st.success("✅ Analysis Ready")
        
        if st.session_state.get(f'{key}_word_bytes'):
            st.download_button(
                label="📄 Download Word Report", 
                data=st.session_state[f'{key}_word_bytes'],
                file_name="ymyl_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True
            )
            
        with st.expander("👁️ View Report Preview", expanded=True):
            st.markdown(st.session_state.get(f'{key}_report', ''))
        
        if st.button("🔄 Start New Analysis"):
            keys = [k for k in st.session_state.keys() if k.startswith(key)]
            for k in keys: del st.session_state[k]
            st.rerun()

    def _get_multi_file_results(self):
        return None
    
    def _show_multi_file_results(self, results):
         pass
