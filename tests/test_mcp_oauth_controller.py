"""Execute the isolated controller logic without an Odoo database."""

import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


CONTROLLER = Path(__file__).resolve().parents[1] / "facodi_mcp_oauth/controllers/consent.py"


def load_controller():
    http = types.ModuleType("odoo.http")
    http.Controller = object
    http.route = lambda *args, **kwargs: lambda fn: fn
    http.request = types.SimpleNamespace(render=lambda template, values, **kw: (template, values, kw))
    odoo = types.ModuleType("odoo")
    odoo.http = http
    spec = importlib.util.spec_from_file_location("test_monynha_consent_controller", CONTROLLER)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"odoo": odoo, "odoo.http": http}):
        spec.loader.exec_module(module)
    return module


class ConsentControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.controller = load_controller()

    def test_publishable_key_required_and_secret_key_rejected(self):
        clients = '["allowed-client"]'
        for key in ("", "sb_secret_very_sensitive", "eyJhbGciOiJIUzI1NiJ9.anonymous.jwt"):
            with self.subTest(key=key[:10]), patch.dict(os.environ, {
                "MONYNHA_OAUTH_SUPABASE_PUBLISHABLE_KEY": key,
                "MONYNHA_OAUTH_ALLOWED_CLIENT_IDS": clients,
            }, clear=True):
                self.assertIsNone(self.controller.public_consent_configuration())

    def test_empty_malformed_or_unapproved_client_list_is_denied(self):
        for raw in ("[]", "not-json", '{"id":"x"}', '[1]', '[""]'):
            with self.subTest(raw=raw), patch.dict(os.environ, {
                "MONYNHA_OAUTH_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_public",
                "MONYNHA_OAUTH_ALLOWED_CLIENT_IDS": raw,
            }, clear=True):
                self.assertIsNone(self.controller.public_consent_configuration())

    def test_valid_client_configuration_renders_without_secret_or_cache(self):
        with patch.dict(os.environ, {
            "MONYNHA_OAUTH_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_public",
            "MONYNHA_OAUTH_ALLOWED_CLIENT_IDS": '["allowed-client"]',
        }, clear=True):
            result = self.controller.MonynhaOAuthConsentController().oauth_consent(
                authorization_id="a1234567-aaaa-bbbb-cccc-dddddddddddd"
            )
        self.assertEqual(result[0], "facodi_mcp_oauth.consent_page")
        self.assertEqual(result[1]["supabase_url"], "https://wvkjainfwsyiyfcmbtid.supabase.co")
        self.assertEqual(result[1]["allowed_clients"], '["allowed-client"]')
        self.assertIn(("Cache-Control", "no-store"), result[2]["headers"])

    def test_missing_authorization_id_never_loads_consent_page(self):
        with patch.dict(os.environ, {
            "MONYNHA_OAUTH_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_public",
            "MONYNHA_OAUTH_ALLOWED_CLIENT_IDS": '["allowed-client"]',
        }, clear=True):
            result = self.controller.MonynhaOAuthConsentController().oauth_consent(
                authorization_id="<script>"
            )
        self.assertEqual(result[0], "facodi_mcp_oauth.consent_invalid")
        self.assertEqual(result[2]["status"], 400)


if __name__ == "__main__":
    unittest.main()
