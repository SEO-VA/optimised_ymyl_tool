#!/usr/bin/env python3
"""
YMYL Audit Tool - Main Application Entry Point
Updated: Removed Sidebar controls (moved to Layouts).
"""

import streamlit as st
from core.auth import check_authentication, logout, get_current_user, is_current_user_admin
from core.state import state_manager
from ui.user_layout import UserLayout
from ui.admin_layout import AdminLayout
from core.google_oauth import handle_callback

# Configure Streamlit page
st.set_page_config(
    page_title="YMYL Audit Tool",
    page_icon="🔍",
    layout="wide" # Using wide for better visibility of logs
)

def main():
    """Main application entry point"""

    # 0. Handle Google OAuth2 callback (must be before any rendering)
    if handle_callback():
        st.rerun()

    # 1. Authentication Barrier
    if not check_authentication():
        return
    
    current_user = get_current_user()
    is_admin = is_current_user_admin()
    
    # 2. Global Header & Navigation
    _render_header(current_user)
    
    # 3. Layout Routing
    try:
        # Feature Selection (Now in Main Area for visibility)
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown("### 🎯 Select Task")
            analysis_type = st.radio(
                "Choose Analysis Type:",
                ["🌐 URL Analysis", "📄 HTML Analysis"],
                label_visibility="collapsed",
                key="main_analysis_type",
                disabled=state_manager.is_processing
            )
        
        st.divider()

        # Map selection to internal feature ID
        feature_key = "url_analysis" if "URL" in analysis_type else "html_analysis"
        
        if is_admin:
            layout = AdminLayout()
            layout.render(feature_key)
        else:
            layout = UserLayout()
            layout.render(feature_key)
            
    except Exception as e:
        st.error(f"❌ Application Error: {str(e)}")
        with st.expander("Details"):
            st.code(str(e))

def _render_header(username: str):
    """Renders the consistent top header"""
    col1, col2 = st.columns([6, 1])
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
