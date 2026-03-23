#!/usr/bin/env python3
"""
Authentication Module
Google OIDC auth for production with an optional local bypass for development.
"""

from typing import Any, Iterable, Optional

import streamlit as st

from utils.helpers import safe_log


_AUTHENTICATED_KEY = "authenticated"
_USERNAME_KEY = "username"
_AUTH_MODE_KEY = "auth_mode"
_LOCAL_BYPASS_MODE = "local_bypass"
_OIDC_MODE = "oidc"
_GOOGLE_PROVIDER = "google"


def check_authentication() -> bool:
    """Main auth check. Returns True if the current user can access the app."""
    _initialize_auth_state()

    bypass_username = _get_local_bypass_username()
    if bypass_username:
        _set_authenticated_user(bypass_username, _LOCAL_BYPASS_MODE)
        safe_log(f"Auth: Local bypass enabled for {bypass_username}")
        return True

    native_auth_error = _get_native_auth_error()
    if native_auth_error:
        _render_login_screen()
        st.error(f"❌ {native_auth_error}")
        return False

    config_error = _get_auth_config_error()
    if config_error:
        _render_login_screen()
        st.error(f"❌ Configuration Error: {config_error}")
        return False

    if not _is_oidc_logged_in():
        _clear_local_auth_state()
        _render_login_screen()
        return False

    email = _extract_user_email(_get_streamlit_user())
    if not email:
        _clear_local_auth_state()
        _render_identity_error()
        return False

    allowed_domain = _get_allowed_domain()
    if not _email_matches_domain(email, allowed_domain):
        _clear_local_auth_state()
        safe_log(f"Auth: Access denied for non-company user {email}", "WARNING")
        _render_access_denied(email, allowed_domain)
        return False

    email = email.lower()
    _set_authenticated_user(email, _OIDC_MODE)
    safe_log(f"Auth: Google login accepted for {email}")
    return True


def logout():
    """Log out the current user."""
    should_logout_oidc = _is_oidc_logged_in() or st.session_state.get(_AUTH_MODE_KEY) == _OIDC_MODE
    _clear_local_auth_state()

    if should_logout_oidc and hasattr(st, "logout"):
        st.logout()


def get_current_user() -> str:
    """Return the current username/email, if available."""
    if st.session_state.get(_AUTH_MODE_KEY) == _LOCAL_BYPASS_MODE:
        return st.session_state.get(_USERNAME_KEY, "Anonymous")

    email = _extract_user_email(_get_streamlit_user())
    if email:
        return email.lower()

    return st.session_state.get(_USERNAME_KEY, "Anonymous")


def is_current_user_admin() -> bool:
    """Return True if the current user should receive the admin layout."""
    if st.session_state.get(_AUTH_MODE_KEY) == _LOCAL_BYPASS_MODE:
        return True

    current_user = get_current_user().strip().lower()
    if not current_user or current_user == "anonymous":
        return False

    admin_emails = {email.lower() for email in _normalize_string_list(_get_auth_settings().get("admin_emails", []))}
    return current_user in admin_emails


def _initialize_auth_state():
    if _AUTHENTICATED_KEY not in st.session_state:
        st.session_state[_AUTHENTICATED_KEY] = False
    if _USERNAME_KEY not in st.session_state:
        st.session_state[_USERNAME_KEY] = None
    if _AUTH_MODE_KEY not in st.session_state:
        st.session_state[_AUTH_MODE_KEY] = None


def _set_authenticated_user(username: str, auth_mode: str):
    st.session_state[_AUTHENTICATED_KEY] = True
    st.session_state[_USERNAME_KEY] = username
    st.session_state[_AUTH_MODE_KEY] = auth_mode


def _clear_local_auth_state():
    st.session_state[_AUTHENTICATED_KEY] = False
    st.session_state[_USERNAME_KEY] = None
    st.session_state[_AUTH_MODE_KEY] = None


def _render_login_screen():
    st.markdown("# 🔐 YMYL Audit Tool")
    st.markdown("### Sign in with your company Google account")
    st.caption("Access is restricted to approved company users.")

    provider_name = _get_provider_name()
    if st.button("🔐 Continue with Google", type="primary", use_container_width=True):
        if provider_name:
            st.login(provider_name)
        else:
            st.login()


def _render_identity_error():
    st.markdown("# 🔐 YMYL Audit Tool")
    st.error("❌ Google login succeeded, but the identity provider did not return an email address.")
    st.caption("Please sign out and try again with a company Google account.")
    st.button("🚪 Sign out", type="primary", use_container_width=True, on_click=logout)


def _render_access_denied(email: str, allowed_domain: str):
    st.markdown("# 🔐 YMYL Audit Tool")
    st.error(f"❌ Access denied for `{email}`.")
    st.caption(f"This app is restricted to `{allowed_domain}` Google accounts.")
    st.button("🚪 Sign out and choose another account", type="primary", use_container_width=True, on_click=logout)


def _get_auth_settings():
    return st.secrets.get("auth", {})


def _get_local_bypass_username() -> Optional[str]:
    """
    Optional local-only bypass controlled through gitignored secrets.toml.
    """
    auth_settings = _get_auth_settings()
    if not auth_settings.get("bypass_local_auth", False):
        return None
    return str(auth_settings.get("bypass_username", "local-dev")).strip() or "local-dev"


def _get_native_auth_error() -> Optional[str]:
    missing_apis = [name for name in ("login", "logout", "user") if not hasattr(st, name)]
    if not missing_apis:
        return None
    return (
        "This Streamlit runtime does not support native OIDC auth yet. "
        "Upgrade to a recent Streamlit release and install `streamlit[auth]`."
    )


def _get_auth_config_error() -> Optional[str]:
    auth_settings = _get_auth_settings()
    missing_shared = [key for key in ("redirect_uri", "cookie_secret", "allowed_domain") if not auth_settings.get(key)]
    if missing_shared:
        return f"`auth.{missing_shared[0]}` missing in secrets.toml"

    provider_name = _get_provider_name()
    provider_settings = auth_settings.get(provider_name, {}) if provider_name else auth_settings
    missing_provider = [
        key for key in ("client_id", "client_secret", "server_metadata_url")
        if not provider_settings.get(key)
    ]
    if missing_provider:
        prefix = f"auth.{provider_name}" if provider_name else "auth"
        return f"`{prefix}.{missing_provider[0]}` missing in secrets.toml"

    return None


def _get_provider_name() -> Optional[str]:
    auth_settings = _get_auth_settings()
    configured_provider = auth_settings.get("provider")
    if configured_provider:
        return str(configured_provider).strip()

    if _GOOGLE_PROVIDER in auth_settings:
        return _GOOGLE_PROVIDER

    return None


def _get_allowed_domain() -> str:
    auth_settings = _get_auth_settings()
    allowed_domain = str(auth_settings.get("allowed_domain", "")).strip().lower()
    return allowed_domain.lstrip("@")


def _is_oidc_logged_in() -> bool:
    user = _get_streamlit_user()
    return bool(_read_user_field(user, "is_logged_in", False))


def _get_streamlit_user():
    return getattr(st, "user", None)


def _extract_user_email(user: Any) -> Optional[str]:
    email = _read_user_field(user, "email")
    if not email:
        return None
    email = str(email).strip()
    return email or None


def _read_user_field(user: Any, field_name: str, default: Any = None) -> Any:
    if user is None:
        return default
    if hasattr(user, field_name):
        return getattr(user, field_name)
    if isinstance(user, dict):
        return user.get(field_name, default)
    try:
        return user[field_name]
    except Exception:
        return default


def _email_matches_domain(email: str, allowed_domain: str) -> bool:
    if not email or not allowed_domain or "@" not in email:
        return False
    return email.lower().split("@", 1)[1] == allowed_domain.lower()


def _normalize_string_list(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = list(value)
    return [str(item).strip() for item in raw_items if str(item).strip()]
