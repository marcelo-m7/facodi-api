import io
import json
import os

from odoo import http
from odoo.http import request
from odoo.modules.module import get_manifest
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge, ServiceUnavailable, Unauthorized
from werkzeug.wrappers import Response

from ..core.contracts.http_input import InvalidPayload, PayloadTooLarge, read_request_object
from ..core.contracts.webhook_auth import WebhookAuthenticationError, WebhookConfigurationError, verify_stripe, verify_supabase


class FacodiApiController(http.Controller):
    @http.route("/facodi/api/v1/health", type="http", auth="public", methods=["GET"], csrf=False)
    def health(self, **kwargs):
        payload = {
            "status": "ok",
            "service": "facodi_api",
            "version": get_manifest("facodi_api")["version"],
        }
        return Response(json.dumps(payload), status=200, mimetype="application/json")

    def _authenticated_webhook_data(self, provider):
        secret = os.getenv(f"FACODI_{provider.upper()}_WEBHOOK_SECRET") or ""
        if not secret.strip():
            raise ServiceUnavailable("Webhook authentication is not configured")
        header = "X-Facodi-Signature" if provider == "supabase" else "Stripe-Signature"
        signature = request.httprequest.headers.get(header)
        if not signature:
            raise Unauthorized("Webhook signature is required")
        request.httprequest.max_content_length = 262145
        body = request.httprequest.get_data(cache=False)
        if len(body) > 262144:
            raise RequestEntityTooLarge("Payload too large")
        verifier = verify_supabase if provider == "supabase" else verify_stripe
        try:
            verifier(body, signature, secret)
        except WebhookConfigurationError:
            raise ServiceUnavailable("Webhook authentication is not configured") from None
        except WebhookAuthenticationError:
            raise Unauthorized("Invalid webhook signature") from None
        try:
            return read_request_object(io.BytesIO(body), len(body), terminated=True)
        except PayloadTooLarge:
            raise RequestEntityTooLarge("Payload too large") from None
        except InvalidPayload:
            raise BadRequest("Invalid JSON body") from None

    @http.route(
        "/facodi/api/v1/supabase/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        max_content_length=262145,
    )
    def supabase_webhook(self, **kwargs):
        data = self._authenticated_webhook_data("supabase")

        request.env["facodi.api.event"].sudo().create(
            {
                "name": "supabase_webhook",
                "provider": "supabase",
                "event_type": "webhook",
                "request_id": data.get("id") or "supabase-webhook",
                "status": "accepted",
                "payload": data,
                "metadata": {"source": "supabase"},
            }
        )
        return Response(json.dumps({"status": "accepted"}), status=202, mimetype="application/json")

    @http.route(
        "/facodi/api/v1/stripe/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        max_content_length=262145,
    )
    def stripe_webhook(self, **kwargs):
        data = self._authenticated_webhook_data("stripe")
        request.env["facodi.api.event"].sudo().create(
            {
                "name": "stripe_webhook",
                "provider": "stripe",
                "event_type": data.get("type") or "webhook",
                "request_id": data.get("id") or "stripe-webhook",
                "status": "accepted",
                "payload": data,
                "metadata": {"source": "stripe"},
            }
        )
        return Response(json.dumps({"status": "accepted"}), status=202, mimetype="application/json")
