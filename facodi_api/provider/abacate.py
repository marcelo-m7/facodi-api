import hashlib
import hmac
import os

try:
    import requests
except ImportError:  # pragma: no cover
    class _MissingRequests:
        post = None

    requests = _MissingRequests()

from .base import ProviderAdapter


class AbacatePayProvider(ProviderAdapter):
    name = "abacate"

    def _resolved_base_url(self):
        base_url = (
            self.config.get("base_url")
            or self.config.get("url")
            or os.getenv("ABACATE_PAY_BASE_URL")
            or os.getenv("ABACATE_PAY_URL")
            or "https://api.abacatepay.com"
        )
        if not base_url:
            raise RuntimeError("Abacate Pay configuration is missing")
        return base_url.rstrip("/")

    def _resolved_api_key(self):
        api_key = (
            self.config.get("api_key")
            or self.config.get("key")
            or os.getenv("ABACATE_PAY_API_KEY")
            or os.getenv("ABACATE_PAY_KEY")
            or ""
        )
        if not api_key:
            raise RuntimeError("Abacate Pay configuration is missing")
        return api_key

    def _resolved_secret(self):
        secret = (
            self.config.get("secret")
            or os.getenv("ABACATE_PAY_SECRET_KEY")
            or os.getenv("ABACATE_PAY_SECRET")
            or ""
        )
        if not secret:
            raise RuntimeError("Abacate Pay configuration is missing")
        return secret

    def _endpoint_for(self, function_name):
        if function_name in {"checkout.session.create", "payment.session.create", "checkout.create"}:
            return f"{self._resolved_base_url()}/api/v1/checkout/sessions"
        if function_name in {"payment.link.create", "checkout.link.create", "payment.link"}:
            return f"{self._resolved_base_url()}/api/v1/payment-links"
        if function_name in {"webhook.construct_event", "webhook.verify"}:
            return f"{self._resolved_base_url()}/api/v1/webhooks/verify"
        raise RuntimeError(f"Unsupported Abacate Pay function: {function_name}")

    def _json_headers(self):
        api_key = self._resolved_api_key()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Api-Key": api_key,
            "Content-Type": "application/json",
            "user-agent": "FACODI-Odoo/19 AbacatePayProvider",
        }
        return headers

    def _verify_webhook(self, payload):
        raw_body = payload.get("raw_body")
        signature = payload.get("signature")
        endpoint_secret = payload.get("endpoint_secret") or self._resolved_secret()
        if not (raw_body and signature):
            raise RuntimeError("Missing Abacate Pay webhook fields")

        computed = hmac.new(
            endpoint_secret.encode("utf-8"),
            raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, computed):
            raise RuntimeError("Invalid Abacate Pay webhook signature")
        return {"verified": True, "signature": signature}

    def dispatch(self, function_name, payload):
        if requests.post is None:
            raise RuntimeError("requests package is not installed")

        if function_name in {"webhook.construct_event", "webhook.verify"}:
            return self._verify_webhook(payload or {})

        endpoint = self._endpoint_for(function_name)
        response = requests.post(
            endpoint,
            json=payload or {},
            headers=self._json_headers(),
            timeout=30,
        )
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            text = getattr(response, "text", "")
            return {"status": "ok", "raw": text}
