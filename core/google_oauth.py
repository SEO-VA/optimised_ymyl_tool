#!/usr/bin/env python3
"""
Google OAuth2 for Drive/Docs access.
Handles the authorization flow to let users grant the app access to create
Google Docs in their own Drive — no service account or admin delegation needed.

Secrets.toml format:
    [google_docs]
    client_id = "..."
    client_secret = "..."
    redirect_uri = "http://localhost:8501"
"""

import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]

_SESSION_KEY = "gdoc_credentials"
_STATE_KEY = "gdoc_oauth_state"


def _get_flow() -> Flow:
    cfg = st.secrets["google_docs"]
    client_config = {"web": {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uris": [cfg["redirect_uri"]],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}
    return Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=cfg["redirect_uri"]
    )


def get_auth_url() -> str:
    """Generate the Google OAuth2 consent URL and store state."""
    flow = _get_flow()
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return auth_url


def handle_callback() -> bool:
    """
    Check st.query_params for an OAuth callback. If found, exchange the code
    for credentials and store them in session state.
    Returns True if a callback was handled (caller should st.rerun()).
    """
    params = st.query_params
    if "code" not in params:
        return False

    try:
        flow = _get_flow()
        flow.fetch_token(code=params["code"])
        creds = flow.credentials
        st.session_state[_SESSION_KEY] = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        }
    except Exception as e:
        st.session_state.pop(_STATE_KEY, None)
        st.error(f"❌ Google authorization failed: {e}")
        return False

    st.session_state.pop(_STATE_KEY, None)
    st.query_params.clear()
    return True


def get_credentials() -> Credentials | None:
    """Return valid Credentials from session state, refreshing if expired."""
    stored = st.session_state.get(_SESSION_KEY)
    if not stored:
        return None

    creds = Credentials(
        token=stored["token"],
        refresh_token=stored.get("refresh_token"),
        token_uri=stored["token_uri"],
        client_id=stored["client_id"],
        client_secret=stored["client_secret"],
        scopes=stored["scopes"],
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            st.session_state[_SESSION_KEY]["token"] = creds.token
        except Exception:
            st.session_state.pop(_SESSION_KEY, None)
            return None

    return creds if creds.valid else None


def clear_credentials():
    st.session_state.pop(_SESSION_KEY, None)
    st.session_state.pop(_STATE_KEY, None)
