#!/usr/bin/env python3

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import google_oauth
from core.models import Severity, Violation
from ui import external_links


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


def build_valid_state(identity, code_verifier, issued_at, snapshot_context=""):
    return google_oauth._encode_state({
        "v": 1,
        "identity": identity,
        "snapshot_context": snapshot_context,
        "iat": issued_at,
        "nonce": "nonce-123",
        "code_verifier": code_verifier,
    })


class GoogleOAuthTests(unittest.TestCase):
    def setUp(self):
        self.fake_st = FakeStreamlit()
        self.log_patcher = patch.object(google_oauth, "safe_log", lambda *args, **kwargs: None)
        self.st_patcher = patch.object(google_oauth, "st", self.fake_st)
        self.snapshot_store = {}
        self.log_patcher.start()
        self.st_patcher.start()

    def tearDown(self):
        self.st_patcher.stop()
        self.log_patcher.stop()

    def _patch_snapshot_store(self):
        def save_json(path, payload):
            self.snapshot_store[path] = payload

        def load_json(path):
            return self.snapshot_store.get(path)

        def delete_file(path):
            self.snapshot_store.pop(path, None)

        return patch.multiple(
            google_oauth,
            _save_json=save_json,
            _load_json=load_json,
            _delete_file=delete_file,
        )

    def test_get_auth_url_emits_signed_state_with_identity_and_verifier(self):
        flows = FlowFactory()

        with patch.object(google_oauth, "_get_flow", side_effect=flows), \
             patch.object(google_oauth, "_get_state_now", return_value=1_700_000_000), \
             patch.object(google_oauth.secrets, "token_urlsafe", side_effect=["verifier-123", "nonce-456"]):
            auth_url = google_oauth.get_auth_url("User@Example.com", snapshot_context="user:url_analysis")
            decoded_state = google_oauth._decode_state(flows.calls[0].authorization_kwargs["state"])

        self.assertEqual(auth_url, "https://accounts.google.com/o/oauth2/auth")
        self.assertEqual(flows.calls[0].code_verifier, "verifier-123")
        self.assertEqual(decoded_state["identity"], "User@Example.com")
        self.assertEqual(decoded_state["code_verifier"], "verifier-123")
        self.assertEqual(decoded_state["nonce"], "nonce-456")
        self.assertEqual(decoded_state["snapshot_context"], "user:url_analysis")

    def test_prepare_auth_url_saves_snapshot_before_generating_auth_url(self):
        calls = []

        def fake_save(identity, context, session_keys):
            calls.append(("save", identity, context, session_keys))
            return True

        def fake_auth(identity, snapshot_context=""):
            calls.append(("auth", identity, snapshot_context))
            return "https://accounts.google.com/o/oauth2/auth"

        with patch.object(google_oauth, "save_analysis_snapshot", side_effect=fake_save), \
             patch.object(google_oauth, "get_auth_url", side_effect=fake_auth):
            auth_url = google_oauth.prepare_auth_url(
                "user@example.com",
                "user:url_analysis",
                ["user_analysis_url_analysis_report"],
            )

        self.assertEqual(auth_url, "https://accounts.google.com/o/oauth2/auth")
        self.assertEqual(
            calls,
            [
                ("save", "user@example.com", "user:url_analysis", ["user_analysis_url_analysis_report"]),
                ("auth", "user@example.com", "user:url_analysis"),
            ],
        )

    def test_handle_callback_succeeds_with_fresh_session_and_signed_state(self):
        flows = FlowFactory()
        saved = {}
        state_value = build_valid_state("user@example.com", "verifier-abc", 1_700_000_000, "user:url_analysis")
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
        self.assertEqual(
            self.fake_st.session_state[google_oauth._CALLBACK_SNAPSHOT_KEY],
            {"identity": "user@example.com", "context": "user:url_analysis"},
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

    def test_save_and_restore_analysis_snapshot_round_trips_result_state(self):
        self.fake_st.session_state.update({
            "main_analysis_type": "🌐 URL Analysis",
            "test_warning_dismissed": True,
            "user_extracted_url_analysis": '{"sections":[]}',
            "user_analysis_url_analysis_complete": True,
            "user_analysis_url_analysis_report": "# Report",
            "user_analysis_url_analysis_word_bytes": b"doc-bytes",
            "user_analysis_url_analysis_violations": [
                Violation(
                    problematic_text="Bad claim",
                    violation_type="Medical claim",
                    explanation="Needs evidence",
                    guideline_section="2.1",
                    page_number=4,
                    severity=Severity.HIGH,
                    suggested_rewrite="Safer wording",
                )
            ],
            "user_source_url_analysis": "https://example.com",
            "user_section_selection_url_analysis": ["Intro"],
        })

        with self._patch_snapshot_store(), \
             patch.object(google_oauth, "_get_state_now", return_value=1_700_000_000):
            saved = google_oauth.save_analysis_snapshot(
                "user@example.com",
                "user:url_analysis",
                [
                    "main_analysis_type",
                    "test_warning_dismissed",
                    "user_extracted_url_analysis",
                    "user_analysis_url_analysis_complete",
                    "user_analysis_url_analysis_report",
                    "user_analysis_url_analysis_word_bytes",
                    "user_analysis_url_analysis_violations",
                    "user_source_url_analysis",
                    "user_section_selection_url_analysis",
                ],
            )

            self.assertTrue(saved)

            self.fake_st.session_state = {}
            restored = google_oauth.restore_analysis_snapshot("user@example.com", "user:url_analysis")

        self.assertTrue(restored)
        self.assertEqual(self.fake_st.session_state["main_analysis_type"], "🌐 URL Analysis")
        self.assertTrue(self.fake_st.session_state["test_warning_dismissed"])
        self.assertEqual(self.fake_st.session_state["user_analysis_url_analysis_word_bytes"], b"doc-bytes")
        restored_violations = self.fake_st.session_state["user_analysis_url_analysis_violations"]
        self.assertEqual(len(restored_violations), 1)
        self.assertEqual(restored_violations[0].severity, Severity.HIGH)
        self.assertEqual(restored_violations[0].problematic_text, "Bad claim")
        self.assertEqual(self.snapshot_store, {})

    def test_restore_analysis_snapshot_ignores_wrong_user_or_context(self):
        self.fake_st.session_state["user_analysis_url_analysis_report"] = "# Report"

        with self._patch_snapshot_store(), \
             patch.object(google_oauth, "_get_state_now", return_value=1_700_000_000):
            google_oauth.save_analysis_snapshot(
                "user@example.com",
                "user:url_analysis",
                ["user_analysis_url_analysis_report"],
            )

            self.fake_st.session_state = {}
            self.assertFalse(google_oauth.restore_analysis_snapshot("other@example.com", "user:url_analysis"))
            self.assertEqual(self.fake_st.session_state, {})
            self.assertFalse(google_oauth.restore_analysis_snapshot("user@example.com", "admin:url_analysis"))
            self.assertEqual(self.fake_st.session_state, {})
            self.assertTrue(google_oauth.restore_analysis_snapshot("user@example.com", "user:url_analysis"))
            self.assertEqual(
                self.fake_st.session_state["user_analysis_url_analysis_report"],
                "# Report",
            )

    def test_callback_restore_recovers_saved_analysis_snapshot(self):
        flows = FlowFactory()
        self.fake_st.session_state.update({
            "main_analysis_type": "🌐 URL Analysis",
            "test_warning_dismissed": True,
            "user_extracted_url_analysis": '{"sections":[]}',
            "user_analysis_url_analysis_complete": True,
            "user_analysis_url_analysis_report": "# Report",
            "user_analysis_url_analysis_word_bytes": b"doc-bytes",
            "user_analysis_url_analysis_violations": [
                Violation(
                    problematic_text="Bad claim",
                    violation_type="Medical claim",
                    explanation="Needs evidence",
                    guideline_section="2.1",
                    page_number=4,
                    severity=Severity.HIGH,
                    suggested_rewrite="Safer wording",
                )
            ],
            "user_source_url_analysis": "https://example.com",
            "user_section_selection_url_analysis": ["Intro"],
        })

        with self._patch_snapshot_store(), \
             patch.object(google_oauth, "_get_flow", side_effect=flows), \
             patch.object(google_oauth, "_get_state_now", return_value=1_700_000_000), \
             patch.object(google_oauth, "_save_to_file", side_effect=lambda *args, **kwargs: None):
            google_oauth.save_analysis_snapshot(
                "user@example.com",
                "user:url_analysis",
                [
                    "main_analysis_type",
                    "test_warning_dismissed",
                    "user_extracted_url_analysis",
                    "user_analysis_url_analysis_complete",
                    "user_analysis_url_analysis_report",
                    "user_analysis_url_analysis_word_bytes",
                    "user_analysis_url_analysis_violations",
                    "user_source_url_analysis",
                    "user_section_selection_url_analysis",
                ],
            )

            self.fake_st.session_state = {}
            self.fake_st.query_params.update({
                "code": "auth-code",
                "state": build_valid_state("user@example.com", "verifier-abc", 1_700_000_000, "user:url_analysis"),
            })

            handled = google_oauth.handle_callback()
            restored = google_oauth.restore_pending_analysis_snapshot()

        self.assertTrue(handled)
        self.assertTrue(restored)
        self.assertEqual(self.fake_st.session_state["main_analysis_type"], "🌐 URL Analysis")
        self.assertTrue(self.fake_st.session_state["test_warning_dismissed"])
        self.assertEqual(self.fake_st.session_state["user_analysis_url_analysis_word_bytes"], b"doc-bytes")
        restored_violations = self.fake_st.session_state["user_analysis_url_analysis_violations"]
        self.assertEqual(len(restored_violations), 1)
        self.assertEqual(restored_violations[0].violation_type, "Medical claim")
        self.assertNotIn(google_oauth._CALLBACK_SNAPSHOT_KEY, self.fake_st.session_state)
        self.assertEqual(self.snapshot_store, {})

    def test_restore_pending_analysis_snapshot_handles_missing_snapshot(self):
        self.fake_st.session_state[google_oauth._CALLBACK_SNAPSHOT_KEY] = {
            "identity": "user@example.com",
            "context": "user:url_analysis",
        }

        with self._patch_snapshot_store():
            restored = google_oauth.restore_pending_analysis_snapshot()

        self.assertFalse(restored)
        self.assertNotIn(google_oauth._CALLBACK_SNAPSHOT_KEY, self.fake_st.session_state)


class ExternalLinksTests(unittest.TestCase):
    def test_render_same_tab_auth_link_outputs_safe_same_tab_markup(self):
        class FakeStreamlit:
            def __init__(self):
                self.calls = []

            def markdown(self, body, unsafe_allow_html=False):
                self.calls.append((body, unsafe_allow_html))

        fake_st = FakeStreamlit()

        with patch.object(external_links, "st", fake_st):
            external_links.render_same_tab_auth_link(
                "Authorize <Google>",
                "https://accounts.google.com/o/oauth2/auth?state=a&next=<home>",
            )

        self.assertEqual(len(fake_st.calls), 1)
        body, unsafe_allow_html = fake_st.calls[0]
        self.assertTrue(unsafe_allow_html)
        self.assertIn('target="_self"', body)
        self.assertIn("Authorize &lt;Google&gt;", body)
        self.assertIn("state=a&amp;next=&lt;home&gt;", body)


if __name__ == "__main__":
    unittest.main()
