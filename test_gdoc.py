#!/usr/bin/env python3
"""
Standalone test for Google Doc creation.
Run with: .venv/bin/python test_gdoc.py
"""

import json
import tomllib
import sys
from pathlib import Path

# --- Load secrets directly from toml (no Streamlit needed) ---
secrets_path = Path(".streamlit/secrets.toml")
if not secrets_path.exists():
    print("ERROR: .streamlit/secrets.toml not found")
    sys.exit(1)

with open(secrets_path, "rb") as f:
    secrets = tomllib.load(f)

sa_info = secrets.get("google_docs", {}).get("service_account")
if not sa_info:
    print("ERROR: [google_docs.service_account] not found in secrets.toml")
    sys.exit(1)

print(f"Service account email: {sa_info.get('client_email')}")
print(f"Project ID: {sa_info.get('project_id')}")
print(f"Token URI: {sa_info.get('token_uri')}")
print()

# --- Build credentials ---
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    SCOPES = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    print(f"✅ Credentials created OK (service_account_email={creds.service_account_email})")
except Exception as e:
    print(f"❌ Credentials error: {e}")
    sys.exit(1)

# --- Test 1: Create a Google Doc (as service account) ---
print("\n[Test 1] Creating Google Doc as service account...")
try:
    docs = build("docs", "v1", credentials=creds)
    doc = docs.documents().create(body={"title": "GDoc API Test"}).execute()
    doc_id = doc["documentId"]
    print(f"✅ Doc created: https://docs.google.com/document/d/{doc_id}/edit")
except Exception as e:
    print(f"❌ Failed: {e}")
    print("\n→ Try with domain-wide delegation (impersonate a user):")

    TEST_USER = "victor.artufel@gamelounge.com"
    print(f"  Impersonating {TEST_USER}...")
    try:
        creds_dwd = creds.with_subject(TEST_USER)
        docs_dwd = build("docs", "v1", credentials=creds_dwd)
        doc = docs_dwd.documents().create(body={"title": "GDoc API Test (DWD)"}).execute()
        doc_id = doc["documentId"]
        print(f"  ✅ Doc created with DWD: https://docs.google.com/document/d/{doc_id}/edit")
        print(f"\n  → FIX: Add .with_subject(user_email) to _build_clients in gdoc_exporter.py")
    except Exception as e2:
        print(f"  ❌ DWD also failed: {e2}")
    sys.exit(1)

# --- Test 2: Share the doc ---
print("\n[Test 2] Sharing doc with victor.artufel@gamelounge.com...")
try:
    drive = build("drive", "v3", credentials=creds)
    drive.permissions().create(
        fileId=doc_id,
        body={"type": "user", "role": "writer", "emailAddress": "victor.artufel@gamelounge.com"},
        sendNotificationEmail=False,
    ).execute()
    print("✅ Shared OK")
except Exception as e:
    print(f"❌ Share failed: {e}")

print("\nDone.")
