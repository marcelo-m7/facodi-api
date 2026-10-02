import os
import unittest
from unittest import mock

from facodi_api.provider.registry import get_provider, list_providers
from facodi_api.service import FacodiApiService


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class ProviderContractTest(unittest.TestCase):
    def test_registry_exposes_core_providers(self):
        providers = set(list_providers())
        self.assertTrue({"supabase", "stripe"}.issubset(providers))
        self.assertIsNotNone(get_provider("supabase"))
        self.assertIsNotNone(get_provider("stripe"))

    def test_supabase_dispatch_uses_env_and_returns_payload(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SECRET_KEY": "secret-key"}, clear=False), mock.patch("facodi_api.provider.supabase.requests.post", return_value=FakeResponse({"ok": True})) as request_mock:
            result = FacodiApiService.dispatch(
                "supabase",
                "video-ingest",
                {"slide_id": 42, "title": "Demo"},
            )

        self.assertEqual(result, {"ok": True})
        request_mock.assert_called_once()

    def test_supabase_requires_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                FacodiApiService.dispatch("supabase", "video-ingest", {"slide_id": 42})

    def test_stripe_dispatch_uses_secret_key(self):
        fake_module = type("FakeStripe", (), {})
        fake_checkout = type("FakeCheckout", (), {"Session": type("Session", (), {"create": staticmethod(lambda **kwargs: {"id": "cs_123", "status": "open"})})})
        fake_module.checkout = fake_checkout
        fake_module.Webhook = type("Webhook", (), {"construct_event": staticmethod(lambda *args, **kwargs: {"ok": "constructed"})})

        with mock.patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_123"}, clear=False), mock.patch.dict("sys.modules", {"stripe": fake_module}):
            result = FacodiApiService.dispatch(
                "stripe",
                "checkout.session.create",
                {"mode": "payment", "line_items": [{"price": "price_123", "quantity": 1}]},
            )

        self.assertEqual(result["id"], "cs_123")


if __name__ == "__main__":
    unittest.main()
