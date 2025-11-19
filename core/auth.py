#!/usr/bin/env python3
"""
Authentication Module
Simple username/password check using Streamlit secrets.
"""

import streamlit as st
from utils.helpers import safe_log

def check_authentication() -> bool:
    """Main auth check. Returns True if logged in."""
    # Initialize session state for auth if it doesn't exist
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.username = None
    
    # If already authenticated, return True
    if st.session_state.authenticated:
        return True
        
    # Otherwise, show the login form
    return _show_login_form()

def _show_login_form() -> bool:
    """Renders login UI."""
    st.markdown("# 🔐 YMYL Audit Tool")
    st.markdown("### Please log in to continue")
    
    # Check if secrets are configured correctly
    if "auth" not in st.secrets or "users" not in st.secrets["auth"]:
        st.error("❌ Configuration Error: 'auth.users' missing in secrets.toml")
        return False

    # Get users from secrets
    users = st.secrets["auth"]["users"]
    
    with st.form("login_form"):
        username = st.text_input("👤 Username")
        password = st.text_input("🔑 Password", type="password")
        submit = st.form_submit_button("🚀 Login", type="primary")
        
        if submit:
            if username in users and users[username] == password:
                st.session_state.authenticated = True
                st.session_state.username = username
                safe_log(f"Auth: User {username} logged in")
                st.rerun()
                return True
            else:
                st.error("❌ Invalid credentials")
                
    return False

def logout():
    """Log out the user."""
    st.session_state.authenticated = False
    st.session_state.username = None

def get_current_user() -> str:
    """Get current username."""
    return st.session_state.get('username', 'Anonymous')
