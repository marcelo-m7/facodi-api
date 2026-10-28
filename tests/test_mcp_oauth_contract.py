"""Pure contract checks for the optional Open2 OAuth consent Website addon."""

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "facodi_mcp_oauth"


class OAuthConsentAddonContract(unittest.TestCase):
    def test_standalone_website_addon_without_business_data_permissions(self):
        manifest = ast.literal_eval((ROOT / "__manifest__.py").read_text())
        self.assertEqual(manifest["depends"], ["website"])
        self.assertIn("views/consent.xml", manifest["data"])
        self.assertTrue(manifest["installable"])
        self.assertFalse((ROOT / "security/ir.model.access.csv").exists())

    def test_page_preserves_site_url_and_renders_public_config_only(self):
        source = (ROOT / "controllers/consent.py").read_text()
        self.assertIn('"/oauth/consent"', source)
        self.assertIn('auth="public"', source)
        self.assertIn("MONYNHA_OAUTH_SUPABASE_PUBLISHABLE_KEY", source)
        self.assertIn("MONYNHA_OAUTH_ALLOWED_CLIENT_IDS", source)
        self.assertNotIn("SUPABASE_SECRET_KEY", source)
        self.assertNotIn("service_role", source)
        self.assertIn("503", source)

    def test_consent_ui_uses_browser_sdk_and_has_both_decisions(self):
        page = (ROOT / "views/consent.xml").read_text()
        bundle_source = (ROOT / "static/src/consent_app.mjs").read_text()
        self.assertIn("website.layout", page)
        self.assertIn('id="monynha-oauth-approve"', page)
        self.assertIn('id="monynha-oauth-deny"', page)
        self.assertIn('type="password"', page)
        self.assertIn("@supabase/supabase-js", bundle_source)
        self.assertIn("createConsentFlow", bundle_source)


if __name__ == "__main__":
    unittest.main()
