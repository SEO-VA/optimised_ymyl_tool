#!/usr/bin/env python3
"""
Google OAuth2 for Drive/Docs access.
Credentials are persisted to /tmp keyed by the current app identity so they survive
Streamlit session resets caused by OAuth redirects.

Secrets.toml format:
    [google_docs]
    client_id = "..."
    client_secret = "..."
    redirect_uri = "http://localhost:8501"
"""

import hashlib
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
_PENDING_SESSION_KEY = "gdoc_oauth_pending"
_STORAGE_DIR = "/tmp"


def _normalize_identity(identity: str = "") -> str:
    identity = str(identity or "").strip()
    return identity or "default"


def _storage_path(prefix: str, identity: str) -> str:
    digest = hashlib.sha256(_normalize_identity(identity).encode("utf-8")).hexdigest()[:16]
    return os.path.join(_STORAGE_DIR, f"{prefix}_{digest}.json")


def _token_path(identity: str) -> str:
    return _storage_path("gdoc_token", identity)


def _pending_path(identity: str) -> str:
    return _storage_path("gdoc_pending", identity)


def _save_json(path: str, payload: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(payload, f)
    except Exception:
        pass


def _load_json(path: str) -> dict | None:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _delete_file(path: str):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _save_to_file(identity: str, creds_dict: dict):
    _save_json(_token_path(identity), creds_dict)


def _load_from_file(identity: str) -> dict | None:
    return _load_json(_token_path(identity))


def _save_pending(identity: str, pending: dict):
    st.session_state[_PENDING_SESSION_KEY] = pending
    _save_json(_pending_path(identity), pending)


def _load_pending(identity: str) -> dict | None:
    pending = st.session_state.get(_PENDING_SESSION_KEY)
    if pending and pending.get("identity") == identity:
        return pending

    pending = _load_json(_pending_path(identity))
    if pending:
        st.session_state[_PENDING_SESSION_KEY] = pending
    return pending


def _clear_pending(identity: str = ""):
    st.session_state.pop(_PENDING_SESSION_KEY, None)
    if identity:
        _delete_file(_pending_path(identity))


def _get_flow(code_verifier: str | None = None) -> Flow:
    cfg = st.secrets["google_docs"]
    client_config = {"web": {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uris": [cfg["redirect_uri"]],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=cfg["redirect_uri"],
        code_verifier=code_verifier,
    )


def get_auth_url(user_email: str = "") -> str:
    """Generate the Google OAuth2 consent URL and persist PKCE state."""
    identity = _normalize_identity(user_email)
    flow = _get_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=identity,
    )
    _save_pending(identity, {
        "identity": identity,
        "state": state,
        "code_verifier": flow.code_verifier,
    })
    return auth_url


def handle_callback() -> bool:
    """
    Check st.query_params for an OAuth callback. If found, exchange the code
    for credentials and persist them. Returns True if handled.
    """
    params = st.query_params
    if "code" not in params:
        return False

    identity = _normalize_identity(params.get("state", ""))
    pending = _load_pending(identity)

    if not pending or not pending.get("code_verifier"):
        st.query_params.clear()
        _clear_pending(identity)
        st.error("❌ Google authorization failed: missing saved code verifier. Please authorize again.")
        return False

    try:
        flow = _get_flow(code_verifier=pending["code_verifier"])
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
        _save_to_file(identity, creds_dict)
    except Exception as e:
        st.query_params.clear()
        _clear_pending(identity)
        st.error(f"❌ Google authorization failed: {e}")
        return False

    _clear_pending(identity)
    st.query_params.clear()
    return True


def get_credentials(user_email: str = "") -> Credentials | None:
    """Return valid Credentials, loading from file if session was reset."""
    identity = _normalize_identity(user_email)
    stored = st.session_state.get(_SESSION_KEY)

    # Session was reset (OAuth redirect) — try loading from file
    if not stored:
        stored = _load_from_file(identity)
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
            _save_to_file(identity, stored)
        except Exception:
            st.session_state.pop(_SESSION_KEY, None)
            return None

    return creds if creds.valid else None


def clear_credentials(user_email: str = ""):
    identity = _normalize_identity(user_email)
    st.session_state.pop(_SESSION_KEY, None)
    _clear_pending(identity)
    _delete_file(_token_path(identity))
