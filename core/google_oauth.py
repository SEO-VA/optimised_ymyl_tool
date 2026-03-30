#!/usr/bin/env python3
"""
Google OAuth2 for Drive/Docs access.
Credentials are persisted to /tmp keyed by the current app identity so they survive
Streamlit session resets caused by OAuth redirects.

OAuth callback recovery is stateless: the PKCE verifier and identity are embedded in a
signed, time-limited OAuth state payload so redirects work even when Streamlit creates
an entirely fresh session.

Secrets.toml format:
    [google_docs]
    client_id = "..."
    client_secret = "..."
    redirect_uri = "http://localhost:8501"
    state_secret = "optional-explicit-secret"
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from core.parser import ResponseParser
from utils.helpers import safe_log

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]

_SESSION_KEY = "gdoc_credentials"
_CALLBACK_SNAPSHOT_KEY = "gdoc_callback_snapshot"
_STORAGE_DIR = "/tmp"
_STATE_MAX_AGE_SECONDS = 15 * 60
_STATE_VERSION = 1
_SNAPSHOT_VERSION = 1
_SNAPSHOT_TYPE_KEY = "__snapshot_type__"
_TOKEN_FIELDS = (
    "token",
    "refresh_token",
    "token_uri",
    "client_id",
    "client_secret",
    "scopes",
)
_VIOLATION_STATE_KEYS = {
    "admin_analysis_violations",
    "user_analysis_url_analysis_violations",
    "user_analysis_html_analysis_violations",
}


def _normalize_identity(identity: str = "") -> str:
    identity = str(identity or "").strip()
    return identity or "default"


def _normalize_snapshot_context(snapshot_context: str = "") -> str:
    snapshot_context = str(snapshot_context or "").strip().lower()
    return snapshot_context or "default"


def _storage_path(prefix: str, identity: str, suffix: str = "") -> str:
    storage_key = f"{_normalize_identity(identity)}:{suffix}" if suffix else _normalize_identity(identity)
    digest = hashlib.sha256(storage_key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(_STORAGE_DIR, f"{prefix}_{digest}.json")


def _token_path(identity: str) -> str:
    return _storage_path("gdoc_token", identity)


def _snapshot_path(identity: str, snapshot_context: str) -> str:
    return _storage_path("gdoc_snapshot", identity, _normalize_snapshot_context(snapshot_context))


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


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _get_state_secret() -> bytes:
    google_cfg = st.secrets.get("google_docs", {})
    explicit_secret = str(google_cfg.get("state_secret", "")).strip()
    cookie_secret = str(st.secrets.get("auth", {}).get("cookie_secret", "")).strip()
    secret_value = explicit_secret or cookie_secret
    if not secret_value:
        raise ValueError("Missing OAuth signing secret. Configure `google_docs.state_secret` or `auth.cookie_secret`.")
    return secret_value.encode("utf-8")


def _get_state_now() -> int:
    return int(time.time())


def _encode_state(payload: dict) -> str:
    secret_bytes = _get_state_secret()
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).digest()
    return f"{_urlsafe_b64encode(payload_bytes)}.{_urlsafe_b64encode(signature)}"


def _decode_state(state_value: str) -> dict:
    try:
        encoded_payload, encoded_signature = state_value.split(".", 1)
    except ValueError as exc:
        raise ValueError("invalid OAuth state signature") from exc

    try:
        payload_bytes = _urlsafe_b64decode(encoded_payload)
        signature = _urlsafe_b64decode(encoded_signature)
    except Exception as exc:
        raise ValueError("invalid OAuth state payload") from exc

    expected_signature = hmac.new(_get_state_secret(), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("invalid OAuth state signature")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid OAuth state payload") from exc

    issued_at = payload.get("iat")
    if not isinstance(issued_at, int):
        raise ValueError("invalid OAuth state timestamp")

    age_seconds = _get_state_now() - issued_at
    if age_seconds < 0 or age_seconds > _STATE_MAX_AGE_SECONDS:
        raise ValueError("expired OAuth state")

    if payload.get("v") != _STATE_VERSION:
        raise ValueError("unsupported OAuth state version")

    if not payload.get("code_verifier"):
        raise ValueError("missing PKCE verifier")

    payload["age_seconds"] = age_seconds
    payload["identity"] = _normalize_identity(payload.get("identity", ""))
    payload["snapshot_context"] = _normalize_snapshot_context(payload.get("snapshot_context", ""))
    return payload


def _build_state_payload(identity: str, code_verifier: str, snapshot_context: str = "") -> dict:
    if not code_verifier:
        raise ValueError("missing PKCE code verifier")
    return {
        "v": _STATE_VERSION,
        "identity": _normalize_identity(identity),
        "snapshot_context": _normalize_snapshot_context(snapshot_context),
        "iat": _get_state_now(),
        "nonce": secrets.token_urlsafe(12),
        "code_verifier": code_verifier,
    }


def _serialize_snapshot_value(value):
    if is_dataclass(value):
        return _serialize_snapshot_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return {
            _SNAPSHOT_TYPE_KEY: "bytes",
            "data": _urlsafe_b64encode(value),
        }
    if isinstance(value, dict):
        return {str(key): _serialize_snapshot_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_snapshot_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _deserialize_snapshot_value(value):
    if isinstance(value, dict):
        if value.get(_SNAPSHOT_TYPE_KEY) == "bytes":
            return _urlsafe_b64decode(value.get("data", ""))
        return {key: _deserialize_snapshot_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deserialize_snapshot_value(item) for item in value]
    return value


def _coerce_snapshot_session_value(key: str, value):
    restored = _deserialize_snapshot_value(value)
    if key in _VIOLATION_STATE_KEYS and isinstance(restored, list):
        violations, _ = ResponseParser.parse_payload_to_violations({"violations": restored})
        return violations
    return restored


def save_analysis_snapshot(user_email: str, snapshot_context: str, session_keys: list[str]) -> bool:
    identity = _normalize_identity(user_email)
    normalized_context = _normalize_snapshot_context(snapshot_context)
    state = {
        key: _serialize_snapshot_value(st.session_state[key])
        for key in session_keys
        if key in st.session_state
    }

    if not state:
        _delete_file(_snapshot_path(identity, normalized_context))
        return False

    payload = {
        "v": _SNAPSHOT_VERSION,
        "identity": identity,
        "context": normalized_context,
        "saved_at": _get_state_now(),
        "state": state,
    }
    _save_json(_snapshot_path(identity, normalized_context), payload)
    safe_log(
        f"GoogleOAuth: Saved analysis snapshot for {identity} ({normalized_context}) with {len(state)} keys"
    )
    return True


def restore_analysis_snapshot(user_email: str, snapshot_context: str) -> bool:
    identity = _normalize_identity(user_email)
    normalized_context = _normalize_snapshot_context(snapshot_context)
    payload = _load_json(_snapshot_path(identity, normalized_context))

    if not payload:
        return False

    if payload.get("v") != _SNAPSHOT_VERSION:
        safe_log(
            f"GoogleOAuth: Ignoring snapshot for {identity} ({normalized_context}) due to version mismatch",
            "WARNING",
        )
        return False

    if payload.get("identity") != identity or payload.get("context") != normalized_context:
        safe_log(
            f"GoogleOAuth: Ignoring snapshot for {identity} ({normalized_context}) due to identity/context mismatch",
            "WARNING",
        )
        return False

    state = payload.get("state", {})
    if not isinstance(state, dict):
        safe_log(
            f"GoogleOAuth: Ignoring snapshot for {identity} ({normalized_context}) because state was invalid",
            "WARNING",
        )
        return False

    for key, value in state.items():
        st.session_state[key] = _coerce_snapshot_session_value(key, value)

    _delete_file(_snapshot_path(identity, normalized_context))
    safe_log(
        f"GoogleOAuth: Restored analysis snapshot for {identity} ({normalized_context}) with {len(state)} keys"
    )
    return True


def restore_pending_analysis_snapshot() -> bool:
    pending = st.session_state.pop(_CALLBACK_SNAPSHOT_KEY, None)
    if not isinstance(pending, dict):
        return False
    return restore_analysis_snapshot(
        pending.get("identity", ""),
        pending.get("context", ""),
    )


def clear_analysis_snapshot(user_email: str, snapshot_context: str):
    _delete_file(_snapshot_path(user_email, snapshot_context))


def _build_creds_dict(creds: Credentials, identity: str) -> dict:
    return {
        "identity": _normalize_identity(identity),
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }


def _stored_identity_matches(stored: dict, identity: str) -> bool:
    return _normalize_identity(stored.get("identity", "")) == _normalize_identity(identity)


def _coerce_stored_credentials(stored: dict | None, identity: str, source: str) -> dict | None:
    if not stored:
        return None

    required_missing = [field for field in _TOKEN_FIELDS if field not in stored]
    if required_missing:
        safe_log(
            f"GoogleOAuth: Ignoring {source} credentials for {identity} missing {required_missing[0]}",
            "WARNING",
        )
        return None

    normalized_identity = _normalize_identity(identity)
    stored_identity = stored.get("identity")

    if stored_identity:
        if not _stored_identity_matches(stored, normalized_identity):
            safe_log(
                f"GoogleOAuth: Ignoring {source} credentials for {normalized_identity} due to identity mismatch",
                "WARNING",
            )
            return None
        stored["identity"] = normalized_identity
        return stored

    if source == "file":
        stored["identity"] = normalized_identity
        _save_to_file(normalized_identity, stored)
        safe_log(f"GoogleOAuth: Migrated legacy token payload for {normalized_identity}")
        return stored

    safe_log(
        f"GoogleOAuth: Ignoring legacy session credentials for {normalized_identity} without identity marker",
        "WARNING",
    )
    return None


def _clear_query_params():
    try:
        st.query_params.clear()
    except Exception:
        pass


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


def get_auth_url(user_email: str = "", snapshot_context: str = "") -> str:
    """Generate the Google OAuth2 consent URL with signed PKCE state."""
    identity = _normalize_identity(user_email)
    code_verifier = secrets.token_urlsafe(64)
    flow = _get_flow(code_verifier=code_verifier)
    state_value = _encode_state(_build_state_payload(identity, code_verifier, snapshot_context))
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state_value,
    )
    safe_log(f"GoogleOAuth: Generated Google Drive auth URL for {identity}")
    return auth_url


def handle_callback() -> bool:
    """
    Check st.query_params for an OAuth callback. If found, exchange the code
    for credentials and persist them. Returns True if handled.
    """
    params = st.query_params
    if "code" not in params:
        return False

    raw_state = str(params.get("state", "")).strip()
    if not raw_state:
        safe_log("GoogleOAuth: Callback failed because OAuth state was missing", "WARNING")
        _clear_query_params()
        st.error("❌ Google authorization failed: missing OAuth state. Please authorize Google Drive again.")
        return False

    try:
        state_payload = _decode_state(raw_state)
        identity = state_payload["identity"]
        snapshot_context = state_payload["snapshot_context"]
        safe_log(
            f"GoogleOAuth: Handling callback for {identity} (state age {state_payload['age_seconds']}s)"
        )
    except ValueError as exc:
        safe_log(f"GoogleOAuth: Callback rejected due to {exc}", "WARNING")
        _clear_query_params()
        st.error(f"❌ Google authorization failed: {exc}. Please authorize Google Drive again.")
        return False

    try:
        flow = _get_flow(code_verifier=state_payload["code_verifier"])
        flow.fetch_token(code=params["code"])
        creds = flow.credentials
        creds_dict = _build_creds_dict(creds, identity)
        st.session_state[_SESSION_KEY] = creds_dict
        st.session_state[_CALLBACK_SNAPSHOT_KEY] = {
            "identity": identity,
            "context": snapshot_context,
        }
        _save_to_file(identity, creds_dict)
        safe_log(f"GoogleOAuth: Stored credentials for {identity}")
    except Exception as exc:
        safe_log(f"GoogleOAuth: Token exchange failed for {identity}: {exc}", "WARNING")
        _clear_query_params()
        st.error(f"❌ Google authorization failed during token exchange: {exc}")
        return False

    _clear_query_params()
    return True


def get_credentials(user_email: str = "") -> Credentials | None:
    """Return valid Credentials, loading from file if session was reset."""
    identity = _normalize_identity(user_email)
    stored = _coerce_stored_credentials(st.session_state.get(_SESSION_KEY), identity, "session")

    if not stored:
        st.session_state.pop(_SESSION_KEY, None)
        stored = _load_from_file(identity)
        stored = _coerce_stored_credentials(stored, identity, "file")
        if stored:
            st.session_state[_SESSION_KEY] = stored

    if not stored:
        safe_log(f"GoogleOAuth: No stored credentials available for {identity}")
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
            stored["refresh_token"] = creds.refresh_token or stored.get("refresh_token")
            st.session_state[_SESSION_KEY] = stored
            _save_to_file(identity, stored)
            safe_log(f"GoogleOAuth: Refreshed credentials for {identity}")
        except Exception as exc:
            safe_log(f"GoogleOAuth: Credential refresh failed for {identity}: {exc}", "WARNING")
            st.session_state.pop(_SESSION_KEY, None)
            _delete_file(_token_path(identity))
            return None

    return creds if creds.valid else None


def clear_credentials(user_email: str = ""):
    identity = _normalize_identity(user_email)
    st.session_state.pop(_SESSION_KEY, None)
    _delete_file(_token_path(identity))
