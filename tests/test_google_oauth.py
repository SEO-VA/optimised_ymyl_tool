#!/usr/bin/env python3

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import google_oauth


class FakeQueryParams(dict):
    def clear(self):
        super().clear()


class FakeStreamlit:
    def __init__(self):
        self.secrets = {
            "google_docs": {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "redirect_uri": "https://app.example.com/oauth/callback",
                "state_secret": "state-secret",
            },
            "auth": {
                "cookie_secret": "cookie-secret",
            },
        }
        self.session_state = {}
        self.query_params = FakeQueryParams()
        self.errors = []

    def error(self, message):
        self.errors.append(message)


class FakeFlow:
    def __init__(self, code_verifier=None):
        self.code_verifier = code_verifier
        self.authorization_kwargs = None
        self.fetch_token_code = None
        self.credentials = SimpleNamespace(
            token="access-token",
            refresh_token="refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret="client-secret",
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )

    def authorization_url(self, **kwargs):
        self.authorization_kwargs = kwargs
        return "https://accounts.google.com/o/oauth2/auth", "google-state"

    def fetch_token(self, code):
        self.fetch_token_code = code


class FlowFactory:
    def __init__(self):
        self.calls = []

    def __call__(self, code_verifier=None):
        flow = FakeFlow(code_verifier=code_verifier)
        self.calls.append(flow)
        return flow


def build_valid_state(identity, code_verifier, issued_at):
    return google_oauth._encode_state({
        "v": 1,
        "identity": identity,
        "iat": issued_at,
        "nonce": "nonce-123",
        "code_verifier": code_verifier,
    })


class GoogleOAuthTests(unittest.TestCase):
    def setUp(self):
        self.fake_st = FakeStreamlit()
        self.log_patcher = patch.object(google_oauth, "safe_log", lambda *args, **kwargs: None)
        self.st_patcher = patch.object(google_oauth, "st", self.fake_st)
        self.log_patcher.start()
        self.st_patcher.start()

    def tearDown(self):
        self.st_patcher.stop()
        self.log_patcher.stop()

    def test_get_auth_url_emits_signed_state_with_identity_and_verifier(self):
        flows = FlowFactory()

        with patch.object(google_oauth, "_get_flow", side_effect=flows), \
             patch.object(google_oauth, "_get_state_now", return_value=1_700_000_000), \
             patch.object(google_oauth.secrets, "token_urlsafe", side_effect=["verifier-123", "nonce-456"]):
            auth_url = google_oauth.get_auth_url("User@Example.com")
            decoded_state = google_oauth._decode_state(flows.calls[0].authorization_kwargs["state"])

        self.assertEqual(auth_url, "https://accounts.google.com/o/oauth2/auth")
        self.assertEqual(flows.calls[0].code_verifier, "verifier-123")
        self.assertEqual(decoded_state["identity"], "User@Example.com")
        self.assertEqual(decoded_state["code_verifier"], "verifier-123")
        self.assertEqual(decoded_state["nonce"], "nonce-456")

    def test_handle_callback_succeeds_with_fresh_session_and_signed_state(self):
        flows = FlowFactory()
        saved = {}
        state_value = build_valid_state("user@example.com", "verifier-abc", 1_700_000_000)
        self.fake_st.query_params.update({"code": "auth-code", "state": state_value})

        def save_to_file(identity, payload):
            saved["identity"] = identity
            saved["payload"] = payload

        with patch.object(google_oauth, "_get_flow", side_effect=flows), \
             patch.object(google_oauth, "_get_state_now", return_value=1_700_000_000), \
             patch.object(google_oauth, "_save_to_file", side_effect=save_to_file):
            handled = google_oauth.handle_callback()

        self.assertTrue(handled)
        self.assertEqual(flows.calls[0].code_verifier, "verifier-abc")
        self.assertEqual(flows.calls[0].fetch_token_code, "auth-code")
        self.assertEqual(saved["identity"], "user@example.com")
        self.assertEqual(
            self.fake_st.session_state[google_oauth._SESSION_KEY]["identity"],
            "user@example.com",
        )
        self.assertEqual(dict(self.fake_st.query_params), {})
        self.assertEqual(self.fake_st.errors, [])

    def test_handle_callback_rejects_tampered_state(self):
        valid_state = build_valid_state("user@example.com", "verifier-abc", 1_700_000_000)
        tampered_state = valid_state[:-1] + ("A" if valid_state[-1] != "A" else "B")
        self.fake_st.query_params.update({"code": "auth-code", "state": tampered_state})

        with patch.object(google_oauth, "_get_state_now", return_value=1_700_000_000):
            handled = google_oauth.handle_callback()

        self.assertFalse(handled)
        self.assertIn("invalid OAuth state", self.fake_st.errors[0])
        self.assertEqual(dict(self.fake_st.query_params), {})

    def test_handle_callback_rejects_expired_state(self):
        expired_state = build_valid_state(
            "user@example.com",
            "verifier-abc",
            1_700_000_000 - google_oauth._STATE_MAX_AGE_SECONDS - 1,
        )
        self.fake_st.query_params.update({"code": "auth-code", "state": expired_state})

        with patch.object(google_oauth, "_get_state_now", return_value=1_700_000_000):
            handled = google_oauth.handle_callback()

        self.assertFalse(handled)
        self.assertIn("expired OAuth state", self.fake_st.errors[0])
        self.assertEqual(dict(self.fake_st.query_params), {})

    def test_handle_callback_requires_state(self):
        self.fake_st.query_params.update({"code": "auth-code"})

        handled = google_oauth.handle_callback()

        self.assertFalse(handled)
        self.assertIn("missing OAuth state", self.fake_st.errors[0])
        self.assertEqual(dict(self.fake_st.query_params), {})

    def test_get_credentials_ignores_mismatched_identity_in_session(self):
        self.fake_st.session_state[google_oauth._SESSION_KEY] = {
            "identity": "bob@example.com",
            "token": "token",
            "refresh_token": "refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "scopes": ["https://www.googleapis.com/auth/drive.file"],
        }

        with patch.object(google_oauth, "_load_from_file", return_value=None):
            creds = google_oauth.get_credentials("alice@example.com")

        self.assertIsNone(creds)
        self.assertNotIn(google_oauth._SESSION_KEY, self.fake_st.session_state)


if __name__ == "__main__":
    unittest.main()
