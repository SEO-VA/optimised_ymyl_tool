#!/usr/bin/env python3
"""
YMYL Audit Tool - Main Application Entry Point
Clean router that handles Authentication and Layout selection.
"""

import streamlit as st
from core.auth import check_authentication, logout, get_current_user
from core.state import state_manager
from utils.feature_registry import FeatureRegistry
from ui.user_layout import UserLayout
from ui.admin_layout import AdminLayout

# Configure Streamlit page
st.set_page_config(
    page_title="YMYL Audit Tool",
    page_icon="🔍",
    layout="centered"
)

def main():
    """Main application entry point"""
    
    # 1. Authentication Barrier
    if not check_authentication():
        return
    
    current_user = get_current_user()
    is_admin = (current_user == 'admin')
    
    # 2. Global Header & Navigation
    _render_header(current_user)
    
    # 3. Global Controls (Sidebar)
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Global Casino Mode (applies to all features)
        # We store this in a standard session key for easy access by layouts
        casino_mode = st.checkbox(
            "🎰 Casino Review Mode",
            help="Use specialized AI assistant for gambling content analysis",
            key="global_casino_mode"
        )
        
        # Emergency Stop (Monitored by Processor)
        if state_manager.is_processing:
            st.error("⚠️ Analysis Running")
            if st.button("🛑 EMERGENCY STOP", type="primary"):
                state_manager.trigger_stop()
                st.rerun()
        
        st.divider()
        
        # Feature Selection
        analysis_type = st.radio(
            "Choose Analysis:",
            ["🌐 URL Analysis", "📄 HTML Analysis"],
            key="main_analysis_type",
            disabled=state_manager.is_processing
        )

    # 4. Routing to Layouts
    try:
        # Map selection to internal feature ID
        feature_key = "url_analysis" if "URL" in analysis_type else "html_analysis"
        
        if is_admin:
            layout = AdminLayout()
            layout.render(feature_key)
        else:
            layout = UserLayout()
            layout.render(feature_key, casino_mode)
            
    except Exception as e:
        st.error(f"❌ Application Error: {str(e)}")
        with st.expander("Details"):
            st.code(str(e))

def _render_header(username: str):
    """Renders the consistent top header"""
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🔍 YMYL Audit Tool")
        st.caption(f"Logged in as: **{username}**")
    with col2:
        if st.button("🚪 Logout", key="main_logout", use_container_width=True):
            logout()
            st.rerun()
    st.divider()

if __name__ == "__main__":
    main()
