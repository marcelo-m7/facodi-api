import os
import unittest
from unittest import mock

if __package__:
    from ..provider.registry import get_provider, list_providers
    from ..service import FacodiApiService
else:
    from facodi_api.provider.registry import get_provider, list_providers
    from facodi_api.service import FacodiApiService


ROOT_MODULE = __package__.rsplit(".tests", 1)[0] if __package__ else "facodi_api"


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
        self.assertTrue({"supabase", "stripe", "abacate"}.issubset(providers))
        self.assertIsNotNone(get_provider("supabase"))
        self.assertIsNotNone(get_provider("stripe"))
        self.assertIsNotNone(get_provider("abacate"))

    def test_supabase_dispatch_uses_env_and_returns_payload(self):
        with mock.patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
            },
            clear=False,
        ), mock.patch(ROOT_MODULE + ".provider.supabase.requests.post", return_value=FakeResponse({"ok": True})) as request_mock:
            result = FacodiApiService.dispatch(
                "supabase",
                "video.ingest",
                {"slide_id": 42, "title": "Demo"},
            )

        self.assertEqual(result, {"ok": True})
        request_mock.assert_called_once()
        endpoint = request_mock.call_args.args[0]
        self.assertEqual(endpoint, "https://example.supabase.co/functions/v1/v3_ingest_youtube_video")
        headers = request_mock.call_args.kwargs["headers"]
        self.assertEqual(headers["apikey"], "sb_secret_test")
        self.assertNotIn("Authorization", headers)

    def test_supabase_video_ingest_allows_explicit_compatibility_override(self):
        with mock.patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
                "FACODI_SUPABASE_VIDEO_INGEST_FUNCTION": "v2_ingest_youtube_video",
            },
            clear=True,
        ), mock.patch(
            ROOT_MODULE + ".provider.supabase.requests.post",
            return_value=FakeResponse({"success": True}),
        ) as request_mock:
            result = FacodiApiService.ingest_video(
                {"url": "https://www.youtube.com/watch?v=SNma-fAeMzA"}
            )

        self.assertEqual(result, {"success": True})
        self.assertEqual(
            request_mock.call_args.args[0],
            "https://example.supabase.co/functions/v1/v2_ingest_youtube_video",
        )

    def test_supabase_uses_project_default_functions(self):
        with mock.patch.dict(
            os.environ,
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SECRET_KEY": "secret-key"},
            clear=False,
        ), mock.patch(ROOT_MODULE + ".provider.supabase.requests.post", return_value=FakeResponse({"status": "ok"})) as request_mock:
            FacodiApiService.analyze_resource({"source_url": "https://example.com/resource"})
            FacodiApiService.discover_metadata({"source_url": "https://example.com/resource"})

        endpoints = [call.args[0] for call in request_mock.call_args_list]
        self.assertIn("https://example.supabase.co/functions/v1/v3_analyze_learning_resource", endpoints)
        self.assertIn("https://example.supabase.co/functions/v1/v3_discover_resource_metadata", endpoints)

    def test_supabase_requires_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                FacodiApiService.dispatch("supabase", "video.ingest", {"slide_id": 42})

    def test_abacate_dispatch_uses_env_and_returns_payload(self):
        with mock.patch.dict(
            os.environ,
            {
                "ABACATE_PAY_API_KEY": "api_key_123",
                "ABACATE_PAY_SECRET_KEY": "secret_key_456",
                "ABACATE_PAY_BASE_URL": "https://api.abacatepay.com",
            },
            clear=False,
        ), mock.patch(ROOT_MODULE + ".provider.abacate.requests.post", return_value=FakeResponse({"id": "pay_123", "status": "open"})) as request_mock:
            result = FacodiApiService.dispatch(
                "abacate",
                "checkout.session.create",
                {"amount": 1000, "currency": "BRL", "description": "Curso FACODI"},
            )

        self.assertEqual(result["id"], "pay_123")
        endpoint = request_mock.call_args.args[0]
        self.assertEqual(endpoint, "https://api.abacatepay.com/api/v1/checkout/sessions")
        self.assertEqual(request_mock.call_args.kwargs["headers"]["Authorization"], "Bearer api_key_123")
        self.assertEqual(request_mock.call_args.kwargs["headers"]["X-Api-Key"], "api_key_123")

    def test_abacate_requires_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                FacodiApiService.dispatch("abacate", "checkout.session.create", {"amount": 1000})

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
