"""Signature verification independent of the Odoo transport and event store."""
import hashlib
import hmac

import stripe


class WebhookConfigurationError(ValueError):
    pass


class WebhookAuthenticationError(ValueError):
    pass


def _require_credentials(signature, secret):
    if not isinstance(secret, str) or not secret.strip():
        raise WebhookConfigurationError("Webhook authentication is not configured")
    if not isinstance(signature, str) or not signature:
        raise WebhookAuthenticationError("Webhook signature is required")


def verify_supabase(body, signature, secret):
    _require_credentials(signature, secret)
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise WebhookAuthenticationError("Invalid webhook signature")


def verify_stripe(body, signature, secret):
    _require_credentials(signature, secret)
    try:
        stripe.Webhook.construct_event(body, signature, secret, tolerance=300)
    except (ValueError, stripe.SignatureVerificationError):
        raise WebhookAuthenticationError("Invalid webhook signature") from None