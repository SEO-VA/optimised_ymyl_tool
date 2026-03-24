#!/usr/bin/env python3
"""
Google OAuth2 for Drive/Docs access.
Credentials are persisted to /tmp keyed by user email so they survive
Streamlit session resets caused by OAuth redirects.

Secrets.toml format:
    [google_docs]
    client_id = "..."
    client_secret = "..."
    redirect_uri = "http://localhost:8501"
"""

import json
import os
import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]

_SESSION_KEY = "gdoc_credentials"


def _token_path(email: str) -> str:
    safe = email.replace("@", "_at_").replace(".", "_")
    return f"/tmp/gdoc_token_{safe}.json"


def _save_to_file(email: str, creds_dict: dict):
    try:
        with open(_token_path(email), "w") as f:
            json.dump(creds_dict, f)
    except Exception:
        pass


def _load_from_file(email: str) -> dict | None:
    path = _token_path(email)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None


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


def get_auth_url(user_email: str = "") -> str:
    """Generate the Google OAuth2 consent URL. Encodes user_email in state."""
    flow = _get_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=user_email,
    )
    return auth_url


def handle_callback() -> bool:
    """
    Check st.query_params for an OAuth callback. If found, exchange the code
    for credentials and persist them. Returns True if handled.
    """
    params = st.query_params
    if "code" not in params:
        return False

    user_email = params.get("state", "")

    try:
        flow = _get_flow()
        flow.fetch_token(code=params["code"])
        creds = flow.credentials
        creds_dict = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        }
        st.session_state[_SESSION_KEY] = creds_dict
        if user_email and "@" in user_email:
            _save_to_file(user_email, creds_dict)
    except Exception as e:
        st.error(f"❌ Google authorization failed: {e}")
        return False

    st.query_params.clear()
    return True


def get_credentials(user_email: str = "") -> Credentials | None:
    """Return valid Credentials, loading from file if session was reset."""
    stored = st.session_state.get(_SESSION_KEY)

    # Session was reset (OAuth redirect) — try loading from file
    if not stored and user_email and "@" in user_email:
        stored = _load_from_file(user_email)
        if stored:
            st.session_state[_SESSION_KEY] = stored

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
            stored["token"] = creds.token
            st.session_state[_SESSION_KEY] = stored
            if user_email:
                _save_to_file(user_email, stored)
        except Exception:
            st.session_state.pop(_SESSION_KEY, None)
            return None

    return creds if creds.valid else None


def clear_credentials(user_email: str = ""):
    st.session_state.pop(_SESSION_KEY, None)
    if user_email:
        try:
            os.remove(_token_path(user_email))
        except FileNotFoundError:
            pass
