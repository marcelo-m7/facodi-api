import os

from .base import ProviderAdapter


class StripeProvider(ProviderAdapter):
    name = "stripe"

    def dispatch(self, function_name, payload):
        api_key = self.config.get("secret") or os.getenv("STRIPE_SECRET_KEY") or ""
        if not api_key:
            raise RuntimeError("Stripe configuration is missing")

        try:
            import stripe as stripe_lib
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("stripe package is not installed") from exc

        if function_name == "checkout.session.create":
            session = stripe_lib.checkout.Session.create(api_key=api_key, **payload)
            return session

        if function_name == "webhook.construct_event":
            sig = payload.get("signature")
            raw_body = payload.get("raw_body")
            endpoint_secret = payload.get("endpoint_secret")
            if not (sig and raw_body and endpoint_secret):
                raise RuntimeError("Missing Stripe webhook fields")
            return stripe_lib.Webhook.construct_event(raw_body, sig, endpoint_secret)

        raise RuntimeError(f"Unsupported Stripe function: {function_name}")
