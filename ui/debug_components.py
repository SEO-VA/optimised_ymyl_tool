#!/usr/bin/env python3
import streamlit as st

def show_debug_results(result, word_bytes):
    """Helper to show raw debug data."""
    st.success("Analysis Complete")
    
    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Processing Time", f"{result.get('processing_time', 0):.1f}s")
    c2.metric("Total Violations", result.get('total_violations_found', 0))
    c3.metric("Unique Violations", result.get('unique_violations', 0))
    
    # Raw Data
    with st.expander("🔬 Raw Orchestrator Data"):
        st.json(result)
        
    # Download
    if word_bytes:
        st.download_button("Download Report", word_bytes, "debug_report.docx")
