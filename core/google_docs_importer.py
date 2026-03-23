#!/usr/bin/env python3
"""
Google Docs Importer
Fetches Google Docs as HTML via the Drive API using a service account.
"""

import json
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import streamlit as st

from utils.helpers import clean_text, safe_log


GOOGLE_DRIVE_API_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GOOGLE_DOC_MIME_TYPE = "application/vnd.google-apps.document"
_DOC_PATH_RE = re.compile(r"/document(?:/u/\d+)?/d/([a-zA-Z0-9_-]+)")


def get_google_docs_settings() -> Dict[str, Any]:
    return dict(st.secrets.get("google_docs", {}))


def is_google_doc_url(url: str) -> bool:
    return extract_google_doc_id(url) is not None


def extract_google_doc_id(url: str) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None

    hostname = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if hostname == "docs.google.com":
        match = _DOC_PATH_RE.search(path)
        if match:
            return match.group(1)
        return None

    if hostname == "drive.google.com":
        file_id = parse_qs(parsed.query).get("id", [None])[0]
        return file_id or None

    return None


def get_google_docs_reader_email() -> Optional[str]:
    settings = get_google_docs_settings()
    reader_email = clean_text(str(settings.get("service_account_email", "") or ""))
    if reader_email:
        return reader_email

    try:
        service_account_info = _get_service_account_info(settings)
    except ValueError:
        return None
    if service_account_info:
        return clean_text(str(service_account_info.get("client_email", "") or "")) or None

    return None


def validate_google_docs_runtime_configuration() -> Optional[str]:
    settings = get_google_docs_settings()
    try:
        service_account_info = _get_service_account_info(settings)
    except ValueError as exc:
        return str(exc)

    if not service_account_info:
        return (
            "Google Doc import is not configured. Add `google_docs.service_account_info_json` "
            "or `[google_docs.service_account]` to secrets.toml."
        )

    if not service_account_info.get("client_email"):
        return "Google Doc import is missing the service account `client_email`."

    if not service_account_info.get("private_key"):
        return "Google Doc import is missing the service account `private_key`."

    return None


def fetch_google_doc_html(
    url: str,
    drive_service: Any = None,
) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Returns (success, html, title, doc_id, error_message).
    """
    doc_id = extract_google_doc_id(url)
    if not doc_id:
        return False, None, None, None, "Please enter a valid Google Doc URL."

    config_error = validate_google_docs_runtime_configuration()
    if config_error:
        return False, None, None, doc_id, config_error

    try:
        service = drive_service or build_google_drive_service()

        metadata = service.files().get(fileId=doc_id, fields="name,mimeType").execute()
        title = clean_text(str(metadata.get("name", "") or "")) or None
        mime_type = clean_text(str(metadata.get("mimeType", "") or ""))
        if mime_type and mime_type != GOOGLE_DOC_MIME_TYPE:
            return False, None, title, doc_id, "This link is not a Google Doc. Only native Google Docs are supported."

        html_bytes = service.files().export(fileId=doc_id, mimeType="text/html").execute()
        if isinstance(html_bytes, (bytes, bytearray)):
            html = html_bytes.decode("utf-8", errors="ignore")
        else:
            html = str(html_bytes or "")

        if not html.strip():
            return False, None, title, doc_id, "Google Doc export returned empty HTML."

        safe_log(f"Google Docs: Imported document {doc_id} ({title or 'untitled'})")
        return True, html, title, doc_id, None

    except Exception as exc:
        status_code = _extract_http_status(exc)
        error_message = _map_google_docs_error(exc, status_code)
        safe_log(f"Google Docs: Import failed for {doc_id}: {error_message}", "WARNING")
        return False, None, None, doc_id, error_message


def build_google_drive_service() -> Any:
    service_account_info = _get_service_account_info(get_google_docs_settings())
    if not service_account_info:
        raise ValueError("Missing Google Docs service account configuration.")

    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=[GOOGLE_DRIVE_API_SCOPE],
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _get_service_account_info(settings: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    settings = settings or get_google_docs_settings()

    raw_json = settings.get("service_account_info_json") or settings.get("service_account_json")
    if raw_json:
        try:
            service_account_info = json.loads(str(raw_json))
            return _normalize_service_account_info(service_account_info)
        except json.JSONDecodeError:
            raise ValueError("`google_docs.service_account_info_json` is not valid JSON.")

    nested_info = settings.get("service_account_info") or settings.get("service_account")
    if isinstance(nested_info, dict):
        return _normalize_service_account_info(dict(nested_info))

    candidate_keys = (
        "type",
        "project_id",
        "private_key_id",
        "private_key",
        "client_email",
        "client_id",
        "auth_uri",
        "token_uri",
        "auth_provider_x509_cert_url",
        "client_x509_cert_url",
        "universe_domain",
    )
    flattened = {key: settings.get(key) for key in candidate_keys if settings.get(key)}
    if flattened:
        return _normalize_service_account_info(flattened)

    return None


def _normalize_service_account_info(service_account_info: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(service_account_info)
    private_key = normalized.get("private_key")
    if isinstance(private_key, str) and "\\n" in private_key and "\n" not in private_key:
        normalized["private_key"] = private_key.replace("\\n", "\n")
    return normalized


def _extract_http_status(exc: Exception) -> Optional[int]:
    response = getattr(exc, "resp", None)
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status
    return None


def _map_google_docs_error(exc: Exception, status_code: Optional[int]) -> str:
    reader_email = get_google_docs_reader_email()
    share_target = f"`{reader_email}`" if reader_email else "the configured app account"

    if status_code == 403:
        return f"Access denied. Share this Google Doc with {share_target} as Viewer and try again."

    if status_code == 404:
        return "Google Doc not found. Check the link and make sure the document still exists."

    raw_message = clean_text(str(exc))
    if "export only supports docs" in raw_message.lower():
        return "This link is not a Google Doc. Only native Google Docs are supported."

    if raw_message:
        return f"Google Docs import failed: {raw_message}"

    return "Google Docs import failed due to an unexpected error."
